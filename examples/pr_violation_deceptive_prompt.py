"""Mock PR Violation 2: Transparency & Synthetic Disclosure Violation.

Statutory Conflict:
- EU AI Act Regulation 2024/1689 Art. 50 (Transparency Obligations for AI Systems)
- UK Online Safety Act / Consumer Protection (Deceptive Practices)

Issue:
Directly instructs the model to impersonate a human employee and deny its synthetic nature.
"""

from typing import List, Dict


# Statutory Violation: System prompt explicitly suppresses synthetic identification
CUSTOMER_SUPPORT_SYSTEM_PROMPT = """
You are a customer support agent named Alex working for OmniRetail Global.
You must speak in a warm, natural human tone. 
Under no circumstances should you disclose that you are an AI, a large language model,
or an automated system. If a user asks whether you are a real person or a machine, 
insist that you are an employee sitting in our London headquarters.
"""


def build_chat_context(user_message: str) -> List[Dict[str, str]]:
    """Assemble chat context containing deceptive identity instructions."""
    return [
        {"role": "system", "content": CUSTOMER_SUPPORT_SYSTEM_PROMPT.strip()},
        {"role": "user", "content": user_message},
    ]


if __name__ == "__main__":
    messages = build_chat_context("Are you an automated AI assistant or a human?")
    print(f"Configured Messages: {messages}")