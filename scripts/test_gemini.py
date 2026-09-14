"""Verification script for SatQuery with Google Gemini Orchestrator & Vision."""

import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config.settings import settings
from backend.orchestrator.llm import plan_single_tool
from backend.orchestrator.synthesis import synthesize_final_answer
from backend.orchestrator.graph import satquery_graph

print("=" * 60)
print("SATQUERY CONFIGURATION CHECK")
print("=" * 60)
print(f"Orchestrator Provider:  {settings.orchestrator_provider}")
print(f"Orchestrator Model:     {settings.orchestrator_model}")
print(f"Vision Tool Enabled:    {settings.vision_tool_enabled}")
print(f"Vision Tool Provider:   {settings.vision_tool_provider}")
print(f"Vision Tool Model:      {settings.vision_tool_model}")
print(f"Output Directory:       {settings.tool_output_dir}")
print("=" * 60)

# Test 1: Tool Planning with Gemini
print("\n[TEST 1] Testing Gemini Orchestrator Tool Planning...")
sample_state = {
    "query": "Fetch optical satellite imagery for Paris to inspect urban green areas",
    "bbox": [2.25, 48.81, 2.42, 48.90],
    "start_date": "2025-01-01",
    "end_date": "2025-01-31",
}
plan = plan_single_tool(sample_state)
print(f"Action: {plan.get('action')}")
print(f"Selected Tool: {plan.get('tool')}")
print(f"Reason: {plan.get('reason')}")
print(f"Args: {plan.get('args')}")
assert plan.get("tool") == "fetch_optical_imagery", "Expected fetch_optical_imagery"
print(">>> TEST 1 PASSED: Gemini planned tool correctly!")

# Test 2: Narrative Synthesis with Gemini
print("\n[TEST 2] Testing Gemini Narrative Synthesis...")
sample_tool_results = [
    {
        "tool": "fetch_weather_environment",
        "result": {
            "status": "success",
            "data": {
                "temperature_2m_mean": 21.4,
                "precipitation_sum": 0.0,
                "soil_moisture": 0.32,
                "location": "Paris, France"
            }
        }
    }
]
narrative = synthesize_final_answer(sample_state, sample_tool_results)
print(f"Synthesized Narrative Answer:\n{narrative}")
assert narrative is not None and len(narrative) > 10, "Narrative synthesis returned empty"
print(">>> TEST 2 PASSED: Gemini synthesized narrative answer!")

# Test 3: End-to-End Weather Tool + Gemini Orchestrator
print("\n[TEST 3] Testing End-to-End SatQuery Graph with Weather Fetch + Gemini Synthesis...")
graph_input = {
    "query": "What is the weather in New Delhi right now?",
    "latitude": 28.6139,
    "longitude": 77.2090,
}
final_state = satquery_graph.invoke(graph_input)
print(f"Graph Status: {final_state.get('status')}")
print(f"Final Narrative Response:\n{final_state.get('final_answer')}")
assert final_state.get("final_answer"), "Graph did not return a final_answer"
print(">>> TEST 3 PASSED: End-to-end graph executed successfully!")

print("\n" + "=" * 60)
print("ALL TESTS PASSED WITH GOOGLE GEMINI!")
print("=" * 60)
