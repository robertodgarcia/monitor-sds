import imaplib
import email
from email.header import decode_header
import time
import requests
import io
import PyPDF2
import os
import datetime
import ssl # Importante para corrigir o erro DH_KEY

# --- CONFIGURAÇÕES ---
# Se estiver na VPS, pode escrever as senhas direto aqui nas aspas se preferir.
# Se estiver no GitHub, deixe os os.getenv.
EMAIL_USER = os.getenv("EMAIL_USER") or "SEU_EMAIL_AQUI" 
EMAIL_PASS = os.getenv("EMAIL_PASS") or "SUA_SENHA_AQUI"
IMAP_SERVER = "imaps.expresso.pe.gov.br"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or "SEU_TOKEN_AQUI"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or "SEU_CHAT_ID"

PALAVRAS_CHAVE = ["DOMINGUEZ", "AGOSTINHO"]

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Erro Telegram: {e}")

def extrair_texto_pdf(payload_bytes):
    texto = ""
    try:
        leitor = PyPDF2.PdfReader(io.BytesIO(payload_bytes))
        for pag in leitor.pages: texto += pag.extract_text() + "\n"
    except: pass
    return texto

def decodificar(header):
    if not header: return ""
    res = ""
    for b, enc in decode_header(header):
        if isinstance(b, bytes):
            try: res += b.decode(enc or 'utf-8', errors='ignore')
            except: res += b.decode('utf-8', errors='ignore')
        else: res += str(b)
    return res

def verificar():
    print(f"Verificando: {datetime.datetime.now()}")
    try:
        # --- CORREÇÃO SSL: Permite chaves antigas ---
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers('DEFAULT@SECLEVEL=1')
        
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, ssl_context=ssl_context)
        # -------------------------------------------
        
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("INBOX")
        
        status, messages = mail.search(None, 'UNSEEN')
        email_ids = messages[0].split()
        
        if not email_ids:
            print("Nenhum e-mail novo.")

        for e_id in email_ids:
            _, msg_data = mail.fetch(e_id, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            
            assunto = decodificar(msg["Subject"])
            remetente = decodificar(msg["From"]).lower()
            assunto_upper = assunto.upper().strip()
            
            print(f"Processando: {assunto}")

            # BIDS
            if assunto_upper.startswith("BIDS"):
                mail.store(e_id, '+FLAGS', '\\Deleted')
                continue
                
            conteudo = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    if ctype == "text/plain":
                        try: conteudo += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        except: pass
                    elif "pdf" in ctype or ".pdf" in str(part.get_filename("")).lower():
                        conteudo += "\n" + extrair_texto_pdf(part.get_payload(decode=True))
            else:
                try: conteudo = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                except: pass
            
            # Busca palavras
            conteudo_upper = conteudo.upper()
            encontradas = [p for p in PALAVRAS_CHAVE if p in conteudo_upper]
            
            if "grafica@policiacivil.pe.gov.br" in remetente and assunto_upper.startswith("BIS"):
                if encontradas:
                    enviar_telegram(f"🚨 **SEU NOME NO BIS!**\n{assunto}\nTermos: {', '.join(encontradas)}")
                else:
                    enviar_telegram(f"ℹ️ **Novo BIS (Sem seu nome)**\n{assunto}")
            
            elif "divport" in remetente and encontradas:
                enviar_telegram(f"⚠️ **CITAÇÃO DIVPORT**\n{assunto}")

        mail.expunge()
        mail.close()
        mail.logout()
        
    except Exception as e:
        print(f"Erro na execução: {e}")

# Se estiver rodando na VPS (Loop infinito):
if __name__ == "__main__":
    while True:
        verificar()
        time.sleep(300)
