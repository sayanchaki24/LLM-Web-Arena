import re
from typing import Dict, Any, List, Optional, Tuple

def compute_heuristics(text: str) -> Dict[str, Any]:
    """Computes objective structural and quantitative metrics for a response."""
    if not text:
        return {
            "word_count": 0,
            "char_count": 0,
            "code_blocks": 0,
            "bullet_points": 0,
            "reading_time_sec": 0,
            "heuristic_score": 0.0
        }

    words = len(text.split())
    chars = len(text)
    code_blocks = len(re.findall(r"```", text)) // 2
    bullet_points = len(re.findall(r"^\s*[-*•]\s", text, re.MULTILINE))
    numbered_lists = len(re.findall(r"^\s*\d+\.\s", text, re.MULTILINE))
    headers = len(re.findall(r"^#{1,6}\s", text, re.MULTILINE))

    reading_time = round((words / 200) * 60)

    # Heuristic scoring (0-100 scale)
    # Balanced reward for substantial content, structure, and formatting
    length_score = min(40, (words / 15))  # max 40 points for ~600 words
    structure_score = min(30, (bullet_points * 3) + (numbered_lists * 3) + (headers * 4))
    code_score = min(20, code_blocks * 10)
    density_score = 10 if (words > 50 and chars / max(1, words) > 4) else 5

    heuristic_score = round(min(100.0, length_score + structure_score + code_score + density_score), 1)

    return {
        "word_count": words,
        "char_count": chars,
        "code_blocks": code_blocks,
        "bullet_points": bullet_points + numbered_lists,
        "reading_time_sec": reading_time,
        "heuristic_score": heuristic_score
    }

def build_judge_prompt(prompt: str, candidate_responses: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """
    Builds an anonymized evaluation prompt.
    Returns (prompt_text, anonymization_mapping).
    anonymization_mapping maps 'Candidate A' -> 'ChatGPT', etc.
    """
    labels = ["Candidate A", "Candidate B", "Candidate C", "Candidate D"]
    mapping = {}
    reverse_mapping = {}

    candidates_text_parts = []
    for idx, (model_name, resp_text) in enumerate(candidate_responses.items()):
        label = labels[idx] if idx < len(labels) else f"Candidate {idx+1}"
        mapping[label] = model_name
        reverse_mapping[model_name] = label
        
        candidates_text_parts.append(f"--- {label} ---\n{resp_text.strip()}\n")

    candidates_formatted = "\n".join(candidates_text_parts)

    judge_prompt = f"""You are an impartial, highly rigorous expert AI evaluation judge.
A user asked the following question:
\"\"\"{prompt.strip()}\"\"\"

Below are {len(candidate_responses)} candidate responses from different AI models, labeled {', '.join(mapping.keys())}.
Your task is to evaluate and compare them strictly on their quality, accuracy, clarity, and usefulness.

{candidates_formatted}

EVALUATION CRITERIA:
1. Accuracy & Correctness (0-10)
2. Completeness & Depth (0-10)
3. Clarity, Formatting & Structure (0-10)
4. Practical Relevance & Directness (0-10)

FORMAT YOUR RESPONSE EXACTLY AS FOLLOWS:
### Detailed Evaluation
- **Candidate A**: [Brief critique] (Score: X/40)
- **Candidate B**: [Brief critique] (Score: Y/40)
...

### Winner Verdict
**WINNER**: [Candidate A or Candidate B...]
**REASON**: [2-3 sentences explaining why this candidate's response is the most helpful and best overall]
"""
    return judge_prompt, mapping

def parse_judge_verdict(judge_response: str, mapping: Dict[str, str]) -> Dict[str, Any]:
    """
    Parses the judge output to extract the winner, the reason, and de-anonymize the results.
    """
    winner_label = None
    reason = "Selected based on comparative evaluation."
    evaluation_summary = judge_response

    # Look for **WINNER**: Candidate X
    winner_match = re.search(r"\*\*WINNER\*\*:\s*(Candidate\s+[A-D]|\w+)", judge_response, re.IGNORECASE)
    if not winner_match:
        winner_match = re.search(r"WINNER:\s*(Candidate\s+[A-D]|\w+)", judge_response, re.IGNORECASE)

    if winner_match:
        raw_winner = winner_match.group(1).strip()
        # Find match in mapping
        for label, model_name in mapping.items():
            if label.lower() in raw_winner.lower():
                winner_label = model_name
                break
        if not winner_label:
            for label, model_name in mapping.items():
                if model_name.lower() in raw_winner.lower():
                    winner_label = model_name
                    break

    # Look for **REASON**: ...
    reason_match = re.search(r"\*\*REASON\*\*:\s*([^\n\r]+(?:\n[^\n\r]+)?)", judge_response, re.IGNORECASE)
    if reason_match:
        reason = reason_match.group(1).strip()

    # De-anonymize evaluation summary text
    deanonymized_summary = judge_response
    for label, model_name in mapping.items():
        deanonymized_summary = re.sub(rf"\b{re.escape(label)}\b", f"**{model_name}** ({label})", deanonymized_summary)

    # Fallback winner if regex failed to extract
    if not winner_label and mapping:
        winner_label = list(mapping.values())[0]

    return {
        "winner": winner_label,
        "reason": reason,
        "evaluation_summary": deanonymized_summary,
        "raw_judge_output": judge_response
    }
