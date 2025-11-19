import imaplib
import email
from email.header import decode_header
import time
import requests
import io
import PyPDF2
import datetime

# --- SUAS CONFIGURAÇÕES ---
EMAIL_USER = "seu_usuario@policiacivil.pe.gov.br" 
EMAIL_PASS = "sua_senha_do_expresso"
IMAP_SERVER = "imaps.expresso.pe.gov.br"

# Telegram
TELEGRAM_TOKEN = "SEU_TOKEN_AQUI"
TELEGRAM_CHAT_ID = "SEU_CHAT_ID_AQUI"

# Palavras-chave (O script converte tudo para maiúsculo automaticamente)
PALAVRAS_CHAVE = ["DOMINGUEZ", "AGOSTINHO"]

def enviar_telegram(mensagem):
    """Envia mensagem para o seu Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Erro ao enviar Telegram: {e}")

def extrair_texto_pdf(payload_bytes):
    """Recebe o arquivo em bytes e devolve o texto dele"""
    texto_completo = ""
    try:
        arquivo_pdf = io.BytesIO(payload_bytes)
        leitor = PyPDF2.PdfReader(arquivo_pdf)
        for pagina in leitor.pages:
            texto_completo += pagina.extract_text() + "\n"
    except Exception as e:
        return "" # Retorna vazio se der erro na leitura
    return texto_completo

def decodificar_texto(header_text):
    """Decodifica assuntos e remetentes que vêm com caracteres estranhos"""
    if not header_text: return ""
    decoded_list = decode_header(header_text)
    texto_final = ""
    for content, encoding in decoded_list:
        if isinstance(content, bytes):
            if encoding:
                try:
                    texto_final += content.decode(encoding)
                except:
                    texto_final += content.decode('utf-8', errors='ignore')
            else:
                texto_final += content.decode('utf-8', errors='ignore')
        else:
            texto_final += str(content)
    return texto_final

def conectar_imap():
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL_USER, EMAIL_PASS)
    return mail

def verificar_emails():
    print(f"--- Verificando em: {datetime.datetime.now().strftime('%H:%M:%S')} ---")
    mail = conectar_imap()
    mail.select("INBOX")
    
    # Busca apenas emails NÃO LIDOS (UNSEEN)
    status, messages = mail.search(None, 'UNSEEN')
    
    email_ids = messages[0].split()
    
    for e_id in email_ids:
        # Baixa o e-mail
        _, msg_data = mail.fetch(e_id, '(RFC822)')
        msg = email.message_from_bytes(msg_data[0][1])
        
        # Decodifica Assunto e Remetente
        assunto = decodificar_texto(msg["Subject"])
        remetente = decodificar_texto(msg["From"]).lower() # converte para minúsculo para facilitar comparação
        
        print(f"Processando: {assunto} | De: {remetente}")
        
        assunto_upper = assunto.upper().strip()
        
        # --- LÓGICA 3: APAGAR BIDS ---
        if assunto_upper.startswith("BIDS"):
            print(">>> BIDS detectado. Apagando...")
            mail.store(e_id, '+FLAGS', '\\Deleted')
            continue # Pula para o próximo e-mail

        encontrou_palavra = False
        palavras_encontradas = []
        conteudo_analisado = ""

        # Processa corpo e anexos
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                # Texto do corpo (apenas se precisar ler, cenário 2)
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        conteudo_analisado += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    except: pass

                # Anexos PDF
                if "application/pdf" in content_type or ".pdf" in part.get_filename("").lower():
                    print("   > PDF encontrado, lendo...")
                    pdf_texto = extrair_texto_pdf(part.get_payload(decode=True))
                    conteudo_analisado += "\n" + pdf_texto

        else:
            # Email texto simples
            try:
                conteudo_analisado = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
            except: pass

        # Verifica as palavras chaves no conteúdo acumulado
        conteudo_upper = conteudo_analisado.upper()
        for palavra in PALAVRAS_CHAVE:
            if palavra in conteudo_upper:
                encontrou_palavra = True
                palavras_encontradas.append(palavra)

        # --- LÓGICA 1: GRÁFICA (BIS) ---
        if "grafica@policiacivil.pe.gov.br" in remetente:
            # Verifica se começa com BIS (removendo espaços extras)
            if assunto_upper.startswith("BIS"):
                if encontrou_palavra:
                    msg_telegram = f"🚨 **ATENÇÃO: SEU NOME NO BIS!**\n\nAssunto: {assunto}\nEncontrado: {', '.join(palavras_encontradas)}"
                else:
                    msg_telegram = f"ℹ️ **Novo BIS Publicado**\n\nAssunto: {assunto}\n(Escaneei e NÃO encontrei seu nome)"
                
                enviar_telegram(msg_telegram)

        # --- LÓGICA 2: DIVPORT ---
        elif "divport@policiacivil.pe.gov.br" in remetente:
            if encontrou_palavra:
                msg_telegram = f"⚠️ **CITAÇÃO NA DIVPORT**\n\nAssunto: {assunto}\nEncontrado: {', '.join(palavras_encontradas)}"
                enviar_telegram(msg_telegram)
            else:
                print("   > DivPort sem palavras-chave. Ignorado.")

    # Confirma a exclusão dos emails marcados (BIDS)
    mail.expunge()
    mail.close()
    mail.logout()

# Loop infinito
print(">>> Monitor de E-mail Policia Civil Iniciado <<<")
while True:
    try:
        verificar_emails()
    except Exception as e:
        print(f"Erro na conexão (tentando novamente em breve): {e}")
        time.sleep(60) # Se der erro, espera 1 minuto e tenta de novo
        continue
        
    time.sleep(300) # Espera 300 segundos (5 minutos)
