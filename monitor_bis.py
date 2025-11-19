import imaplib
import email
from email.header import decode_header
import time
import requests
import io
import PyPDF2
import os
import datetime
import ssl 
import re  # <--- Nova ferramenta para limpar HTML

# --- CONFIGURAÇÕES ---
# GitHub Actions Secrets
EMAIL_USER = os.getenv("EMAIL_USER") 
EMAIL_PASS = os.getenv("EMAIL_PASS")
IMAP_SERVER = "imaps.expresso.pe.gov.br"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PALAVRAS_CHAVE = ["DOMINGUEZ", "AGOSTINHO"]

def enviar_telegram(mensagem):
    print(f" [Telegram] Tentando enviar: {mensagem[:50]}...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f" [Erro Conexão Telegram] {e}")

def extrair_texto_pdf(payload_bytes):
    texto_completo = ""
    try:
        arquivo_pdf = io.BytesIO(payload_bytes)
        leitor = PyPDF2.PdfReader(arquivo_pdf)
        for pagina in leitor.pages:
            texto_completo += pagina.extract_text() + "\n"
    except:
        return ""
    return texto_completo

def extrair_texto_html(payload_bytes):
    """Limpa as tags HTML (<br>, <div>) e deixa só o texto visível"""
    try:
        texto_html = payload_bytes.decode('utf-8', errors='ignore')
        # Regex simples para remover tags HTML
        clean = re.compile('<.*?>')
        texto_limpo = re.sub(clean, ' ', texto_html)
        return texto_limpo
    except:
        return ""

def decodificar_texto(header_text):
    if not header_text: return ""
    decoded_list = decode_header(header_text)
    texto_final = ""
    for content, encoding in decoded_list:
        if isinstance(content, bytes):
            try:
                texto_final += content.decode(encoding if encoding else 'utf-8', errors='ignore')
            except:
                texto_final += content.decode('utf-8', errors='ignore')
        else:
            texto_final += str(content)
    return texto_final

def verificar_emails():
    print(f"--- Iniciando verificação: {datetime.datetime.now()} ---")
    
    if not EMAIL_USER or not EMAIL_PASS:
        print("ERRO CRÍTICO: Credenciais não encontradas (Secrets vazios).")
        return

    try:
        # --- CORREÇÃO SSL ---
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers('DEFAULT@SECLEVEL=1')
        
        print("Conectando ao servidor...")
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, ssl_context=ssl_context)
        
        mail.login(EMAIL_USER, EMAIL_PASS)
        print("Login realizado com sucesso.")
        
        mail.select("INBOX")
        
        # Busca APENAS e-mails novos (não lidos)
        status, messages = mail.search(None, 'UNSEEN')
        email_ids = messages[0].split()
        
        if not email_ids:
            print(" > Nenhum e-mail novo.")
            return
        
        print(f" > Encontrados {len(email_ids)} novos e-mails.")

        for e_id in email_ids:
            _, msg_data = mail.fetch(e_id, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            
            assunto = decodificar_texto(msg["Subject"])
            remetente = decodificar_texto(msg["From"]).lower()
            assunto_upper = assunto.upper().strip()
            
            print(f"   Checando: {assunto} | De: {remetente}")

            # Lógica BIDS (Apagar)
            if assunto_upper.startswith("BIDS"):
                mail.store(e_id, '+FLAGS', '\\Deleted')
                print("   -> BIDS deletado.")
                continue

            # Extração de Conteúdo (Texto, PDF e agora HTML)
            conteudo_analisado = ""
            
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    filename = str(part.get_filename("")).lower()
                    
                    # 1. Texto Simples
                    if ctype == "text/plain":
                        try: conteudo_analisado += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        except: pass
                    
                    # 2. PDF
                    elif "application/pdf" in ctype or ".pdf" in filename:
                        print("      [PDF] Lendo anexo...")
                        conteudo_analisado += "\n" + extrair_texto_pdf(part.get_payload(decode=True))
                    
                    # 3. HTML (Nova funcionalidade)
                    elif "html" in ctype or ".html" in filename or ".htm" in filename:
                        print("      [HTML] Lendo anexo HTML...")
                        conteudo_analisado += "\n" + extrair_texto_html(part.get_payload(decode=True))

            else:
                # Caso o e-mail não tenha anexo, mas o corpo seja HTML puro
                ctype = msg.get_content_type()
                payload = msg.get_payload(decode=True)
                
                if "html" in ctype:
                     conteudo_analisado = extrair_texto_html(payload)
                else:
                     try: conteudo_analisado = payload.decode('utf-8', errors='ignore')
                     except: pass

            # Lógica de Palavras 
            conteudo_upper = conteudo_analisado.upper()
            palavras_encontradas = [p for p in PALAVRAS_CHAVE if p in conteudo_upper]

            if palavras_encontradas:
                print(f"      [!] Encontrou: {palavras_encontradas}")

            # Lógica GRÁFICA
            if "grafica" in remetente and "BIS" in assunto_upper:
                if palavras_encontradas:
                    enviar_telegram(f"🚨 **SEU NOME NO BIS!**\n{assunto}\nTermos: {', '.join(palavras_encontradas)}")
                else:
                    enviar_telegram(f"ℹ️ **Novo BIS Publicado**\n{assunto}\n(Nada encontrado)")
            
            # Lógica DIVPORT
            elif "divport" in remetente:
                if palavras_encontradas:
                    enviar_telegram(f"⚠️ **CITAÇÃO NA DIVPORT**\n{assunto}\nTermos: {', '.join(palavras_encontradas)}")
                else:
                    print("      [Divport] E-mail ignorado (sem palavras chaves).")

        mail.expunge()
        mail.close()
        mail.logout()
        
    except Exception as e:
        print(f"Erro na execução: {e}")

if __name__ == "__main__":
    # Teste de Telegram ao iniciar
    print("🤖 Iniciando script via GitHub Actions...")
    enviar_telegram("🤖 Monitor Rodando (v3.0 com HTML) - Check iniciado.")
    
    verificar_emails()
