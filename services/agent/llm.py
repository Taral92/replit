import logging
from typing import Any
from packages.config import settings

logger = logging.getLogger("RunnerIDE-LLM")

def get_llm(model: str, purpose: str = "agent", temperature: float = 0.1) -> Any:
    """
    Factory for LLM clients. Owns provider selection, OPENAI_BASE_URL routing, 
    API key fallback, and temperature defaults.
    """
    # Metering is attached here, at the single construction point, so a new
    # call site cannot silently skip it.
    from services.agent.metering import UsageCallback
    callbacks = [UsageCallback(model)]

    if settings.local_mode:
        from langchain_openai import ChatOpenAI
        print(f"[Model Runtime] 🖥️ Local model via {settings.OPENAI_BASE_URL} ({model}) for {purpose}")
        return ChatOpenAI(
            model=model,
            api_key=settings.OPENAI_API_KEY or "ollama",
            base_url=settings.OPENAI_BASE_URL,
            temperature=temperature,
            callbacks=callbacks,
            )
    
    # Bedrock mode is exclusive: EVERY request goes to AWS. No model name reaches
    # OpenAI or the Anthropic API, whatever the caller asked for.
    #
    # The `model` argument is ignored on purpose. Callers still pass OpenAI or
    # Anthropic-API ids from older code paths (the verifier's default, the
    # conversational fast path), and Bedrock has never heard of any of them —
    # each would 404. BEDROCK_MODEL is the single source of truth here.
    if settings.bedrock_mode:
        try:
            from langchain_aws import ChatBedrockConverse
        except ImportError:
            raise RuntimeError(
                "USE_BEDROCK is set but 'langchain-aws' is not installed. "
                "Run: pip install langchain-aws boto3. Refusing to fall back to "
                "OpenAI or Anthropic — that would bill a provider you asked to avoid."
            )

        if model != settings.BEDROCK_MODEL:
            print(f"[Model Runtime] ☁️ Bedrock: '{model}' → {settings.BEDROCK_MODEL}")
        print(
            f"[Model Runtime] ☁️ Bedrock ({settings.BEDROCK_MODEL}) "
            f"in {settings.BEDROCK_REGION} for {purpose}"
        )
        return ChatBedrockConverse(
            model=settings.BEDROCK_MODEL,
            region_name=settings.BEDROCK_REGION,
            temperature=temperature,
            callbacks=callbacks,
        )

    if "claude" in model.lower():
        from services.agent.router import ModelRouter
        if not ModelRouter.anthropic_available():
            print(f"[Model Runtime] ⚠️ ANTHROPIC_API_KEY not found. Falling back to {settings.DEFAULT_AGENT_MODEL}")
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=settings.DEFAULT_AGENT_MODEL,
                api_key=settings.OPENAI_API_KEY,
                temperature=temperature,
                callbacks=callbacks,
                )
        try:
            from langchain_anthropic import ChatAnthropic
            print(f"[Model Runtime] 🏆 Initializing native Anthropic Claude ({model})")
            return ChatAnthropic(
                model_name=model,
                api_key=settings.ANTHROPIC_API_KEY,
                temperature=temperature,
                callbacks=callbacks,
                )
        except ImportError:
            print("[Model Runtime] ⚠️ 'langchain-anthropic' package not installed. Falling back to OpenAI.")
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=settings.DEFAULT_AGENT_MODEL,
                api_key=settings.OPENAI_API_KEY,
                temperature=temperature,
                callbacks=callbacks,
                )
            
    # Default to OpenAI
    from langchain_openai import ChatOpenAI
    print(f"[Model Runtime] ⚡ Initializing OpenAI model ({model})")
    
    if "o3" in model:
        temperature = 1.0
        
    return ChatOpenAI(
        model=model,
        api_key=settings.OPENAI_API_KEY,
        temperature=temperature,
        callbacks=callbacks,
        )
