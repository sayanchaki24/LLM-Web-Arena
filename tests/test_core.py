import os
import unittest
from app.evaluator import compute_heuristics, build_judge_prompt, parse_judge_verdict
from app.database import init_db, save_query_record, save_response_record, update_query_evaluation, get_history, get_query_by_id

class TestBestResponseCore(unittest.TestCase):
    def setUp(self):
        init_db()

    def test_compute_heuristics(self):
        sample_text = """
# Introduction to FastAPI

FastAPI is a modern, high-performance web framework for Python.

- Easy to learn
- Fast to code
- Production-ready

```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "ok"}
```
        """
        metrics = compute_heuristics(sample_text)
        self.assertGreater(metrics["word_count"], 10)
        self.assertEqual(metrics["code_blocks"], 1)
        self.assertEqual(metrics["bullet_points"], 3)
        self.assertGreater(metrics["heuristic_score"], 20.0)

    def test_judge_prompt_and_parser(self):
        prompt = "Explain photosynthesis"
        responses = {
            "ChatGPT": "Photosynthesis is the process by which green plants use sunlight to synthesize nutrients from carbon dioxide and water.",
            "Gemini": "Photosynthesis turns solar energy into chemical energy within plant chloroplasts, releasing oxygen.",
            "Claude": "During photosynthesis, light energy absorbed by chlorophyll drives carbon fixation in plant thylakoids.",
            "GLM": "Photosynthesis converts light into chemical energy (glucose) via light-dependent reactions and the Calvin cycle in plant cells."
        }
        judge_prompt, mapping = build_judge_prompt(prompt, responses)
        self.assertIn("Candidate A", judge_prompt)
        self.assertIn("Candidate B", judge_prompt)
        self.assertIn("Candidate C", judge_prompt)
        self.assertIn("Candidate D", judge_prompt)
        self.assertEqual(len(mapping), 4)

        mock_judge_response = """
### Detailed Evaluation
- **Candidate A**: Accurate definition, very accessible. (Score: 36/40)
- **Candidate B**: Clear summary of energy transformation. (Score: 34/40)
- **Candidate C**: Excellent biochemical precision mentioning thylakoids. (Score: 38/40)
- **Candidate D**: Superb balanced overview specifically citing Calvin cycle. (Score: 39/40)

### Winner Verdict
**WINNER**: Candidate D
**REASON**: Candidate D provided the most scientifically comprehensive explanation while maintaining clarity.
        """
        verdict = parse_judge_verdict(mock_judge_response, mapping)
        self.assertEqual(verdict["winner"], "GLM")
        self.assertIn("Candidate D", verdict["reason"] or verdict["raw_judge_output"])

    def test_providers_registered(self):
        from app.providers import PROVIDERS
        self.assertIn("ChatGPT", PROVIDERS)
        self.assertIn("Claude", PROVIDERS)
        self.assertIn("Gemini", PROVIDERS)
        self.assertIn("GLM", PROVIDERS)
        self.assertEqual(PROVIDERS["GLM"].url, "https://chat.z.ai/")

    def test_database_operations(self):
        query_id = save_query_record(
            prompt="What is the speed of light?",
            models_queried=["ChatGPT", "Gemini"]
        )
        self.assertIsInstance(query_id, int)

        save_response_record(
            query_id=query_id,
            model_name="ChatGPT",
            response_text="The speed of light in vacuum is approximately 299,792,458 meters per second.",
            status="success",
            word_count=12,
            char_count=82,
            code_blocks=0,
            elapsed_seconds=1.4
        )

        update_query_evaluation(
            query_id=query_id,
            winner="ChatGPT",
            evaluation_summary="Accurate and concise.",
            judge_reason="Provided the exact SI metric value.",
            judge_model="Gemini"
        )

        item = get_query_by_id(query_id)
        self.assertIsNotNone(item)
        self.assertEqual(item["winner"], "ChatGPT")
        self.assertEqual(len(item["responses"]), 1)
        self.assertEqual(item["responses"][0]["model_name"], "ChatGPT")

        history = get_history(limit=5)
        self.assertGreaterEqual(len(history), 1)

if __name__ == "__main__":
    unittest.main()
