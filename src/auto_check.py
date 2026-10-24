import re
import json
import pytest

def verify_ai_text_numbers(json_input: dict, ai_response_text: str) -> bool:
    """
    Extracts all numerical values from the AI text response using regular expressions
    and programmatically verifies that they exist within the allowed source data fields.
    """
    allowed_source_values = set()
    
    allowed_source_values.add(str(json_input.get("region")))
    allowed_source_values.add(str(json_input.get("period")))
    
    trend_block = json_input.get("trend", {})
    for key, value in trend_block.items():
        if isinstance(value, (int, float)):
            allowed_source_values.add(f"{value}")
            allowed_source_values.add(f"{value:.5f}")
            allowed_source_values.add(f"{value:.4f}")
            allowed_source_values.add(f"{value:.3f}")
            allowed_source_values.add(f"{abs(value)}")
            
    found_numbers = re.findall(r'-?\d+\.?\d*', ai_response_text)
    
    for num in found_numbers:
        clean_num = num.strip(".")
        is_valid = any(clean_num in src_val or src_val in clean_num for src_val in allowed_source_values)
        
        if not is_valid:
            print(f"❌ HALLUCINATION DETECTED: The number '{num}' was found in AI output but does not exist in raw source data.")
            return False
            
    print("✔ VALIDATION PASSED: All numbers match the source data perfectly.")
    return True

# --- Programmatic Pytest Verification Block ---

def test_valid_response_passes():
    mock_json = {
        "region": "Arctic Circle",
        "period": "2006-2026",
        "trend": {"direction": "increasing", "p_value": 0.00001, "tau": 0.72, "slope": 0.045}
    }
    compliant_ai_text = "The Arctic Circle region shows an increasing trend between 2006-2026 with a slope of 0.045 and p_value of 0.00001. This is significant."
    assert verify_ai_text_numbers(mock_json, compliant_ai_text) is True

def test_invented_number_fails():
    mock_json = {
        "region": "Arctic Circle",
        "period": "2006-2026",
        "trend": {"direction": "increasing", "p_value": 0.00001, "tau": 0.72, "slope": 0.045}
    }
    hallucinated_ai_text = "The trend slope is 0.045, showing a general warming of 1.5 degrees over the period."
    assert verify_ai_text_numbers(mock_json, hallucinated_ai_text) is False

if __name__ == "__main__":
    print("Running manual evaluation checks...")
    
    # Run passing case
    test_valid_response_passes()
    
    # Explicitly check that the failure case catches the hallucination
    mock_json = {
        "region": "Arctic Circle",
        "period": "2006-2026",
        "trend": {"direction": "increasing", "p_value": 0.00001, "tau": 0.72, "slope": 0.045}
    }
    hallucinated_ai_text = "The trend slope is 0.045, showing a general warming of 1.5 degrees over the period."
    
    if verify_ai_text_numbers(mock_json, hallucinated_ai_text) == False:
        print("✔ Automated failure simulation verified successfully.")
