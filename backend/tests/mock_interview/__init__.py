"""Backend tests for the ``mock_interview`` module.

The whole suite runs FULLY OFFLINE (see ``tests/conftest.py``): real AI calls are
hard-pinned off, so ``AiTaskRunner.complete/stream`` and ``generate_report`` raise
``AIUnavailableError`` and every LLM path degrades to the module's deterministic
static fallbacks. No test here hits a network provider.
"""
