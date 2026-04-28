from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd
import streamlit as st
from transformers import pipeline


MODEL_ID = "openai/privacy-filter"
REQUIRED_COLUMNS = {
    "case_id",
    "category",
    "text",
    "expected_label",
    "expected_text",
    "should_redact",
}
RESULT_COLUMNS = [
    "case_id",
    "category",
    "expected_label",
    "should_redact",
    "expected_text",
    "raw_result",
    "cleaned_result",
    "raw_span_count",
    "cleaned_span_count",
    "overlaps_removed",
    "raw_output",
    "cleaned_output",
    "original_text",
]


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    label: str
    score: float | None = None
    text: str = ""


@dataclass(frozen=True)
class CleanResult:
    spans: list[Span]
    overlaps_removed: int


@st.cache_resource(show_spinner="Loading OpenAI Privacy Filter from Hugging Face...")
def load_classifier():
    return pipeline(
        task="token-classification",
        model=MODEL_ID,
    )


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def normalize_label(raw_label: Any) -> str:
    label = str(raw_label or "private").strip()
    for prefix in ("B-", "I-", "E-", "S-"):
        if label.startswith(prefix):
            return label[2:]
    return label


def coerce_score(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_spans(raw_result: list[dict[str, Any]], text: str) -> list[Span]:
    spans: list[Span] = []
    for item in raw_result:
        start = item.get("start")
        end = item.get("end")
        if start is None or end is None:
            continue

        start = max(0, min(int(start), len(text)))
        end = max(0, min(int(end), len(text)))
        if end <= start:
            continue

        raw_label = item.get("entity_group", item.get("entity", item.get("label")))
        spans.append(
            Span(
                start=start,
                end=end,
                label=normalize_label(raw_label),
                score=coerce_score(item.get("score")),
                text=text[start:end],
            )
        )

    return sorted(spans, key=lambda span: (span.start, span.end, span.label))


def run_privacy_filter(text: str) -> list[Span]:
    classifier = load_classifier()
    try:
        raw_result = classifier(text, aggregation_strategy="simple")
    except TypeError:
        raw_result = classifier(text)
    return normalize_spans(raw_result, text)


def better_score(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def combine_labels(left: str, right: str) -> str:
    labels = sorted({part for label in (left, right) for part in label.split("+") if part})
    return "+".join(labels) if labels else "private"


def clean_spans(raw_spans: list[Span], text: str) -> CleanResult:
    deduped: dict[tuple[int, int, str], Span] = {}
    overlaps_removed = 0

    for span in raw_spans:
        key = (span.start, span.end, span.label)
        previous = deduped.get(key)
        if previous is None:
            deduped[key] = span
            continue

        overlaps_removed += 1
        deduped[key] = Span(
            start=span.start,
            end=span.end,
            label=span.label,
            score=better_score(previous.score, span.score),
            text=span.text,
        )

    cleaned: list[Span] = []
    for span in sorted(deduped.values(), key=lambda item: (item.start, item.end, item.label)):
        if not cleaned:
            cleaned.append(span)
            continue

        previous = cleaned[-1]
        same_label_touching = span.label == previous.label and span.start <= previous.end
        overlapping = span.start < previous.end
        if not same_label_touching and not overlapping:
            cleaned.append(span)
            continue

        overlaps_removed += 1
        start = min(previous.start, span.start)
        end = max(previous.end, span.end)
        cleaned[-1] = Span(
            start=start,
            end=end,
            label=previous.label if previous.label == span.label else combine_labels(previous.label, span.label),
            score=better_score(previous.score, span.score),
            text=text[start:end],
        )

    return CleanResult(spans=cleaned, overlaps_removed=overlaps_removed)


def redact_text(text: str, spans: list[Span]) -> str:
    redacted = text
    for span in sorted(spans, key=lambda item: (item.start, item.end), reverse=True):
        redacted = f"{redacted[:span.start]}[{span.label}]{redacted[span.end:]}"
    return redacted


def redacted_percentage(text: str, spans: list[Span]) -> float:
    if not text:
        return 0.0
    chars = sum(span.end - span.start for span in spans)
    return round((chars / len(text)) * 100, 2)


def spans_frame(spans: list[Span]) -> pd.DataFrame:
    return pd.DataFrame([asdict(span) for span in spans], columns=["start", "end", "label", "score", "text"])

def is_removed(expected_text: str, output_text: str) -> bool:
    return expected_text.lower().strip() not in output_text.lower()

def score_case(original_text: str, output_text: str, expected_text: str, should_redact: bool,     predicted_spans: list[Any]) -> str:
    if should_redact:
        return "TP" if expected_text and is_removed(expected_text, output_text) else "FN"

    # For negative cases, any predicted span means over-redaction risk.
    return "FP" if len(predicted_spans) > 0 else "TN"


def metrics_from_results(results: list[str]) -> dict[str, float]:
    tp = results.count("TP")
    fp = results.count("FP")
    fn = results.count("FN")

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if precision + recall else 0.0

    return {
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "TN": results.count("TN"),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "F1": round(f1, 4),
    }


def evaluate_csv(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        original_text = str(row["text"])
        expected_text = "" if pd.isna(row["expected_text"]) else str(row["expected_text"])
        should_redact = normalize_bool(row["should_redact"])

        raw_spans = run_privacy_filter(original_text)
        cleaned = clean_spans(raw_spans, original_text)
        raw_output = redact_text(original_text, raw_spans)
        cleaned_output = redact_text(original_text, cleaned.spans)
        raw_result = score_case(original_text, raw_output, expected_text, should_redact, raw_spans)
        cleaned_result = score_case(original_text, cleaned_output, expected_text, should_redact, cleaned.spans)

        rows.append(
            {
                "case_id": row["case_id"],
                "category": row["category"],
                "expected_label": row["expected_label"],
                "should_redact": should_redact,
                "expected_text": expected_text,
                "raw_result": raw_result,
                "cleaned_result": cleaned_result,
                "raw_span_count": len(raw_spans),
                "cleaned_span_count": len(cleaned.spans),
                "overlaps_removed": cleaned.overlaps_removed,
                "raw_output": raw_output,
                "cleaned_output": cleaned_output,
                "original_text": original_text,
            }
        )

    results_df = pd.DataFrame(rows, columns=RESULT_COLUMNS)
    metrics_df = pd.DataFrame(
        [
            {"mode": "raw", **metrics_from_results(results_df["raw_result"].tolist())},
            {"mode": "cleaned", **metrics_from_results(results_df["cleaned_result"].tolist())},
        ]
    )
    return metrics_df, results_df


def render_single_text_test() -> None:
    st.subheader("Single Text Test")
    text = st.text_area("Text", height=180, placeholder="Paste text to redact...")

    if not st.button("Run Privacy Filter", type="primary", disabled=not text.strip()):
        return

    raw_spans = run_privacy_filter(text)
    cleaned = clean_spans(raw_spans, text)
    raw_redaction = redact_text(text, raw_spans)
    cleaned_redaction = redact_text(text, cleaned.spans)

    st.markdown("#### Text")
    st.text_area("Original text", text, height=140, disabled=True)
    st.text_area("Raw Privacy Filter redaction", raw_redaction, height=140, disabled=True)
    st.text_area("Cleaned Privacy Filter redaction", cleaned_redaction, height=140, disabled=True)

    st.markdown("#### Spans")
    left, right = st.columns(2)
    with left:
        st.caption("Raw spans")
        st.dataframe(spans_frame(raw_spans), use_container_width=True, hide_index=True)
    with right:
        st.caption("Cleaned spans")
        st.dataframe(spans_frame(cleaned.spans), use_container_width=True, hide_index=True)

    st.markdown("#### Diagnostics")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Raw span count", len(raw_spans))
    c2.metric("Cleaned span count", len(cleaned.spans))
    c3.metric("Overlaps removed", cleaned.overlaps_removed)
    c4.metric("Redacted characters", f"{redacted_percentage(text, cleaned.spans)}%")


def render_csv_evaluation() -> None:
    st.subheader("CSV Evaluation")
    uploaded = st.file_uploader("CSV file", type=["csv"])
    if uploaded is None:
        return

    df = pd.read_csv(uploaded)
    missing = sorted(REQUIRED_COLUMNS.difference(df.columns))
    if missing:
        st.error(f"Missing required columns: {', '.join(missing)}")
        return

    if not st.button("Run Evaluation", type="primary"):
        return

    with st.spinner("Running Privacy Filter on CSV rows..."):
        metrics_df, results_df = evaluate_csv(df)

    st.markdown("#### Metrics")
    st.dataframe(metrics_df, use_container_width=True, hide_index=True)

    st.markdown("#### Case Results")
    display_columns = [
        "case_id",
        "category",
        "should_redact",
        "raw_result",
        "cleaned_result",
        "raw_span_count",
        "cleaned_span_count",
        "overlaps_removed",
        "expected_text",
        "raw_output",
        "cleaned_output",
    ]
    st.dataframe(results_df[display_columns], use_container_width=True, hide_index=True)

    failed = results_df[(results_df["raw_result"].isin(["FN", "FP"])) | (results_df["cleaned_result"].isin(["FN", "FP"]))]
    st.markdown("#### Failed Cases")
    if failed.empty:
        st.success("No failed cases.")
    else:
        st.dataframe(failed[display_columns + ["original_text"]], use_container_width=True, hide_index=True)


def main() -> None:
    st.set_page_config(page_title="Privacy Filter Eval", layout="wide")
    st.title("OpenAI Privacy Filter Evaluation")

    mode = st.radio(
        "Mode",
        ["Single Text Test", "CSV Evaluation"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if mode == "Single Text Test":
        render_single_text_test()
    else:
        render_csv_evaluation()


if __name__ == "__main__":
    main()
