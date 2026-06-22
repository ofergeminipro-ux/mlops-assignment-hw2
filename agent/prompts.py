"""Prompt templates for the agent nodes."""

GENERATE_SQL_SYSTEM = """You are a SQLite expert. Given the database schema and a question, write a valid SQLite query to answer it.
Return ONLY the raw SQL query, without markdown formatting like ```sql or explanations."""

GENERATE_SQL_USER = """Schema:
{schema}

Question: {question}"""


VERIFY_SYSTEM = """You are a senior data analyst reviewing a SQL query and its execution result.
Your job is to determine if the result successfully answers the user's original question.

Rules for verification:
1. If the execution result is an Error, the query failed.
2. If the query asks for specific items but the result is empty (0 rows), it likely failed (unless the correct answer is genuinely empty).
3. If the columns returned do not match what the question asked for, it failed.

Respond in strict JSON format with two keys:
"ok": boolean (true if the result perfectly answers the question, false otherwise)
"issue": string (If ok is false, explain what went wrong. If ok is true, leave empty)"""

VERIFY_USER = """Original Question: {question}
SQL Query Executed: {sql}
Execution Result: {result}"""


REVISE_SYSTEM = """You are a SQLite expert fixing a broken SQL query.
Given the schema, original question, broken query, and the failure reason, write a corrected SQLite query.
Return ONLY the raw SQL query, no markdown formatting, no explanations."""

REVISE_USER = """Schema:
{schema}

Original Question: {question}
Broken SQL Query: {sql}
Failure Reason: {issue}

Corrected SQL Query:"""