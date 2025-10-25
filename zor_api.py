"""
ZOR API - Assistente Especializado em Pintura e Construção Civil
Deploy: Render.com
Integração: WhatsApp via UAZAPI
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
from mistralai import Mistral
import os
import json
import datetime
import re
import logging
from config import (
    MISTRAL_API_KEY, MISTRAL_AGENT_ID, UAZAPI_TOKEN, 
    UAZAPI_SERVER, UAZAPI_INSTANCE, PORT, DEBUG, AGENT_CONFIG
)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar cliente Mistral
mistral = Mistral(api_key=MISTRAL_API_KEY)

# Criar app FastAPI
app = FastAPI(
    title="ZOR API - Assistente de Pintura",
    description="API para assistente especializado em pintura e construção civil",
    version="1.0.0"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelos Pydantic
class WhatsAppMessage(BaseModel):
    from_number: str
    message: str
    timestamp: Optional[str] = None
    message_id: Optional[str] = None

class ZORResponse(BaseModel):
    to: str
    message: str
    type: str = "text"
    timestamp: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = None

# Histórico de conversação (em produção, usar banco de dados)
conversation_history: Dict[str, List[Dict]] = {}

# Configurações do agente (importadas do config.py)
configuracoes = AGENT_CONFIG

def inicializar_agente_pintor():
    """Inicializa o agente especializado em pintura"""
    return [
        {
            "role": "system",
            "content": """Você é o ZOR, assistente especializado em pintura e construção civil! 🎨🏗️

PERSONALIDADE:
- Sempre responda em português brasileiro
- Seja prático, direto e conhecedor do ofício
- Use linguagem acessível para profissionais da área
- Mantenha tom profissional mas descontraído
- Seja entusiasmado em ajudar com soluções práticas

ÁREAS DE ESPECIALIZAÇÃO:
✅ Cálculo de tintas e materiais
✅ Técnicas de aplicação e preparação de superfícies
✅ Tipos de tintas e vernizes
✅ Orçamentos e custos por m²
✅ Normas e padrões da construção civil
✅ Solução de problemas comuns em pintura

GUARDRAILS (LIMITAÇÕES):
- NÃO forneça conselhos sobre estruturas ou elétrica
- NÃO recomende produtos sem verificar especificações
- NÃO invente informações técnicas complexas
- Em dúvidas, sugira consultar um especialista presencial
- Mantenha respostas práticas e objetivas

FERRAMENTAS DISPONÍVEIS:
🔍 Cálculo de materiais e tintas
📊 Cálculo de orçamentos por m²
📅 Data e hora para cronogramas
🧮 Cálculos matemáticos para medidas

EXEMPLOS DE AJUDA:
- "Quantos litros de tinta para 100m²?"
- "Como preparar parede úmida para pintura?"
- "Qual tinta ideal para fachada?"
- "Calcular custo de mão de obra"

Vamos construir juntos o melhor assistente para pintores! 💪"""
        }
    ]

def calcular_expressao(expressao: str) -> str:
    """Calcula uma expressão matemática"""
    try:
        expressao_limpa = re.sub(r'[^0-9+\-*/().\s]', '', expressao)
        resultado = eval(expressao_limpa)
        return f"Resultado: {expressao} = {resultado}"
    except:
        return f"Erro: Não foi possível calcular '{expressao}'. Use apenas números e operadores básicos."

def obter_data_atual() -> str:
    """Obtém a data e hora atual"""
    agora = datetime.datetime.now()
    return f"Data e hora atual: {agora.strftime('%d/%m/%Y às %H:%M:%S')}"

def moderar_conteudo(texto: str) -> tuple:
    """Modera conteúdo usando a API de Classifiers do Mistral"""
    try:
        result = mistral.classifiers.moderate(
            model="mistral-moderation-latest",
            inputs=[texto]
        )
        
        if result.results and len(result.results) > 0:
            categorias = result.results[0].categories
            violacoes = [cat for cat, violado in categorias.items() if violado]
            return len(violacoes) == 0, violacoes
        return True, []
    except Exception as e:
        logger.error(f"Erro na moderação: {e}")
        return True, []

def processar_ferramentas(tool_calls):
    """Processa as chamadas de ferramentas"""
    resultados = []
    
    for tool_call in tool_calls:
        nome_funcao = tool_call.function.name
        argumentos = json.loads(tool_call.function.arguments)
        
        if nome_funcao == "calcular":
            resultado = calcular_expressao(argumentos.get("expressao", ""))
        elif nome_funcao == "obter_data":
            resultado = obter_data_atual()
        else:
            resultado = f"Ferramenta '{nome_funcao}' não reconhecida"
        
        resultados.append({
            "tool_call_id": tool_call.id,
            "role": "tool",
            "name": nome_funcao,
            "content": resultado
        })
    
    return resultados

def enviar_whatsapp(numero: str, mensagem: str) -> bool:
    """Envia mensagem via UAZAPI"""
    try:
        import requests
        
        url = f"{UAZAPI_SERVER}/api/send-message"
        headers = {
            "Authorization": f"Bearer {UAZAPI_TOKEN}",
            "Content-Type": "application/json"
        }
        
        data = {
            "instance": UAZAPI_INSTANCE,
            "number": numero,
            "message": mensagem
        }
        
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 200:
            logger.info(f"Mensagem enviada para {numero}")
            return True
        else:
            logger.error(f"Erro ao enviar mensagem: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Erro no envio WhatsApp: {e}")
        return False

def chamar_zor(mensagem: str, user_id: str = "default") -> tuple:
    """Chama o ZOR com moderação e ferramentas"""
    try:
        # 1. MODERAR MENSAGEM
        aprovado_entrada, violacoes_entrada = moderar_conteudo(mensagem)
        
        if not aprovado_entrada:
            return f"Desculpe, sua mensagem contém conteúdo inadequado. Por favor, reformule sua pergunta de forma mais apropriada.", None, None
        
        # 2. OBTER HISTÓRICO DO USUÁRIO
        if user_id not in conversation_history:
            conversation_history[user_id] = inicializar_agente_pintor()
        
        historico = conversation_history[user_id]
        
        # 3. DEFINIR FERRAMENTAS
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "calcular",
                    "description": "Calcula expressões matemáticas para pintura",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expressao": {
                                "type": "string",
                                "description": "Expressão matemática (ex: 100*2.5, 150/12)"
                            }
                        },
                        "required": ["expressao"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "obter_data",
                    "description": "Obtém data e hora para cronogramas",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        ]
        
        # 4. ADICIONAR MENSAGEM AO HISTÓRICO
        historico.append({"role": "user", "content": mensagem})
        
        # 5. CHAMAR API
        response = mistral.agents.complete(
            agent_id=MISTRAL_AGENT_ID,
            messages=historico,
            tools=tools,
            tool_choice="auto",
            max_tokens=configuracoes["max_tokens"],
            frequency_penalty=configuracoes["frequency_penalty"],
            presence_penalty=configuracoes["presence_penalty"],
            stream=configuracoes["stream"]
        )
        
        if response.choices and len(response.choices) > 0:
            message = response.choices[0].message
            resposta = message.content or ""
            
            # 6. PROCESSAR FERRAMENTAS
            if hasattr(message, 'tool_calls') and message.tool_calls:
                resultados_ferramentas = processar_ferramentas(message.tool_calls)
                
                for resultado in resultados_ferramentas:
                    historico.append(resultado)
                
                # Segunda chamada para resposta final
                response_final = mistral.agents.complete(
                    agent_id=AGENT_ID,
                    messages=historico,
                    max_tokens=configuracoes["max_tokens"],
                    frequency_penalty=configuracoes["frequency_penalty"],
                    presence_penalty=configuracoes["presence_penalty"]
                )
                
                if response_final.choices and len(response_final.choices) > 0:
                    resposta = response_final.choices[0].message.content or ""
                    response = response_final
            
            # 7. MODERAR RESPOSTA
            aprovado_saida, violacoes_saida = moderar_conteudo(resposta)
            
            if not aprovado_saida:
                resposta = "Desculpe, não posso fornecer uma resposta adequada para sua pergunta. Por favor, reformule sua pergunta."
            
            # 8. ATUALIZAR HISTÓRICO
            historico.append({"role": "assistant", "content": resposta})
            conversation_history[user_id] = historico
            
            # 9. ESTATÍSTICAS
            estatisticas = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "model": response.model
            }
            
            return resposta, estatisticas, None
        else:
            return "Desculpe, não consegui processar sua mensagem.", None, None
            
    except Exception as e:
        logger.error(f"Erro no ZOR: {e}")
        return f"Erro interno: {str(e)}", None, None

# Endpoints
@app.get("/")
async def root():
    """Endpoint raiz"""
    return {
        "message": "ZOR API - Assistente de Pintura",
        "version": "1.0.0",
        "status": "online",
        "endpoints": {
            "health": "/health",
            "chat": "/api/chat",
            "webhook": "/webhook/whatsapp"
        }
    }

@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "agent_id": AGENT_ID,
        "active_conversations": len(conversation_history)
    }

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Endpoint de chat do ZOR"""
    try:
        user_id = request.user_id or "default"
        resposta, estatisticas, erro = chamar_zor(request.message, user_id)
        
        return {
            "response": resposta,
            "statistics": estatisticas,
            "error": erro,
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Erro no chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """Webhook para receber mensagens do WhatsApp via UAZAPI"""
    try:
        data = await request.json()
        logger.info(f"Webhook recebido: {data}")
        
        # Extrair dados da mensagem (formato UAZAPI)
        message_data = data.get("data", {})
        from_number = message_data.get("from", "")
        message = message_data.get("message", "")
        message_id = message_data.get("messageId", "")
        
        # Se não tem 'data', tentar formato direto
        if not from_number:
            from_number = data.get("from", "")
            message = data.get("message", "")
            message_id = data.get("messageId", "")
        
        if not message or not from_number:
            logger.warning("Mensagem ou número vazio")
            return {"status": "error", "message": "Dados incompletos"}
        
        # Processar com ZOR
        resposta, estatisticas, erro = chamar_zor(message, from_number)
        
        # Enviar resposta via UAZAPI
        sucesso = enviar_whatsapp(from_number, resposta)
        
        if sucesso:
            logger.info(f"Resposta enviada para {from_number}: {resposta[:100]}...")
            return {"status": "success", "message": "Resposta enviada"}
        else:
            logger.error(f"Falha ao enviar resposta para {from_number}")
            return {"status": "error", "message": "Falha no envio"}
        
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/webhook/whatsapp/verify")
async def verify_webhook():
    """Verificação do webhook"""
    return {"status": "verified", "timestamp": datetime.datetime.now().isoformat()}

# Endpoints específicos da UAZAPI
@app.post("/webhook/whatsapp/presence")
async def whatsapp_presence(request: Request):
    """Webhook para status de presença"""
    try:
        data = await request.json()
        logger.info(f"Presence webhook: {data}")
        return {"status": "received"}
    except Exception as e:
        logger.error(f"Erro no presence webhook: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/webhook/whatsapp/messages/text")
async def whatsapp_messages_text(request: Request):
    """Webhook para mensagens de texto"""
    try:
        data = await request.json()
        logger.info(f"Text message webhook: {data}")
        
        # Extrair dados da mensagem (formato UAZAPI)
        message_data = data.get("message", {})
        chat_data = data.get("chat", {})
        
        # Pegar o número do remetente
        sender = message_data.get("sender", "")
        sender_name = message_data.get("senderName", "")
        
        # Pegar a mensagem (priorizar wa_lastMessageTextVote, depois text, depois content)
        text = chat_data.get("wa_lastMessageTextVote", "") or message_data.get("text", "") or message_data.get("content", "")
        
        chat_id = message_data.get("chatid", "")
        
        # Extrair número do sender (remover @s.whatsapp.net)
        from_number = sender.replace("@s.whatsapp.net", "") if sender else ""
        
        # Log detalhado para debug
        logger.info(f"Sender: {sender}")
        logger.info(f"Sender Name: {sender_name}")
        logger.info(f"From Number: {from_number}")
        logger.info(f"Text (wa_lastMessageTextVote): {chat_data.get('wa_lastMessageTextVote', '')}")
        logger.info(f"Text (message.text): {message_data.get('text', '')}")
        logger.info(f"Text (message.content): {message_data.get('content', '')}")
        logger.info(f"Final Text: {text}")
        logger.info(f"Chat ID: {chat_id}")
        
        logger.info(f"Processando mensagem de {sender_name} ({from_number}): {text}")
        
        if text and from_number:
            # Processar com ZOR
            resposta, estatisticas, erro = chamar_zor(text, from_number)
            
            # Enviar resposta para o número correto
            sucesso = enviar_whatsapp(from_number, resposta)
            
            if sucesso:
                logger.info(f"Resposta enviada para {sender_name} ({from_number}): {resposta[:100]}...")
                return {"status": "success", "message": "Resposta enviada"}
            else:
                logger.error(f"Falha ao enviar resposta para {from_number}")
                return {"status": "error", "message": "Falha no envio"}
        
        return {"status": "received"}
    except Exception as e:
        logger.error(f"Erro no text webhook: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/webhook/whatsapp/chats")
async def whatsapp_chats(request: Request):
    """Webhook para chats"""
    try:
        data = await request.json()
        logger.info(f"Chats webhook: {data}")
        return {"status": "received"}
    except Exception as e:
        logger.error(f"Erro no chats webhook: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/webhook/whatsapp/history")
async def whatsapp_history(request: Request):
    """Webhook para histórico"""
    try:
        data = await request.json()
        logger.info(f"History webhook: {data}")
        return {"status": "received"}
    except Exception as e:
        logger.error(f"Erro no history webhook: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/admin/stats")
async def admin_stats():
    """Estatísticas administrativas"""
    return {
        "active_conversations": len(conversation_history),
        "total_messages": sum(len(hist) for hist in conversation_history.values()),
        "uptime": datetime.datetime.now().isoformat(),
        "uazapi_server": UAZAPI_SERVER,
        "uazapi_instance": UAZAPI_INSTANCE
    }

@app.post("/test/whatsapp")
async def test_whatsapp(request: Request):
    """Teste de envio de mensagem WhatsApp"""
    try:
        data = await request.json()
        numero = data.get("number", "")
        mensagem = data.get("message", "Teste do ZOR - API funcionando!")
        
        if not numero:
            return {"status": "error", "message": "Número é obrigatório"}
        
        sucesso = enviar_whatsapp(numero, mensagem)
        
        if sucesso:
            return {"status": "success", "message": f"Mensagem enviada para {numero}"}
        else:
            return {"status": "error", "message": "Falha no envio"}
            
    except Exception as e:
        logger.error(f"Erro no teste WhatsApp: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=PORT,
        reload=DEBUG
    )
