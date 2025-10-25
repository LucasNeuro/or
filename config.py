"""
Configurações do ZOR API
"""

import os
from dotenv import load_dotenv

# Carregar variáveis do arquivo .env se existir
load_dotenv()

# Configurações do Mistral AI
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "2MCneGm5mZ7YUXuxXqkFspvhLq5OuyJA")
MISTRAL_AGENT_ID = os.getenv("MISTRAL_AGENT_ID", "ag_019a1cb6944070ffa790ba45f9dc77fc")

# Configurações UAZAPI
UAZAPI_TOKEN = os.getenv("UAZAPI_TOKEN", "B7teYpdEf9I9LM9lxDE5CUqmxF68P2LrwvtF6NZ5eZu2oqqXz3r")
UAZAPI_SERVER = os.getenv("UAZAPI_SERVER", "https://free.uazapi.com")
UAZAPI_INSTANCE = os.getenv("UAZAPI_INSTANCE", "6790bc53-8378-4014-b498-300093ee43af")

# Configurações do servidor
PORT = int(os.getenv("PORT", 8000))
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

# Configurações do agente
AGENT_CONFIG = {
    "max_tokens": 300,
    "frequency_penalty": 0.3,
    "presence_penalty": 0.2,
    "stream": False
}
