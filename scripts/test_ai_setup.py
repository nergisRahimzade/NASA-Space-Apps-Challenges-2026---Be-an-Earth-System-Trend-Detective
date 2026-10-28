import os

from dotenv import load_dotenv
from openai import OpenAI

# 1. Load environment variables from the hidden .env file
load_dotenv()

# 2. Initialize the client (it automatically looks for OPENAI_API_KEY in your env)
client = OpenAI()

def test_connection():
    print("--- Starting AI Layer Setup Verification ---")
    
    # Simple check to make sure the key loaded
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or "your_actual_api_key" in api_key:
        print("❌ Error: Valid OPENAI_API_KEY not found in .env file.")
        return

    print("✅ Successfully read API Key from .env")

    try:
        print("📡 Sending one test prompt to OpenAI...")
        # 3. Send a lightweight test message to the model
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Fast, cheap model perfect for tests/sprints
            messages=[{"role": "user", "content": "Respond with exactly the words: AI Layer Active."}],
            max_tokens=10
        )
        
        # 4. Print the exact text reply
        reply = response.choices[0].message.content.strip()
        print(f"🤖 OpenAI Reply: '{reply}'")
        
        if "AI Layer Active" in reply:
            print("\n🎉 Verification Success! ESD-D01-AI is DONE.")
        
    except Exception as e: # noqa: BLE001
        print(f"❌ API Call Failed: {e}")

if __name__ == "__main__":
    test_connection()

