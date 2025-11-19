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

# --- CONFIGURAÇÕES ---
EMAIL_USER = "seu.usuario"      # <--- SEU LOGIN (sem @ se for o caso)
EMAIL_PASS = "sua_senha"        # <--- SUA SENHA
IMAP_SERVER = "imaps.expresso.pe.gov.br"

TELEGRAM_TOKEN = "SEU_TOKEN_AQUI"    # <--- SEU TOKEN
TELEGRAM_CHAT_ID = "SEU_CHAT_ID"     # <--- SEU CHAT ID

PALAVRAS_CHAVE = ["DOMINGUEZ", "AGOSTINHO"]

def enviar_telegram(mensagem):
    print(f" [Telegram] Enviando: {mensagem[:50]}...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f" [Erro Telegram] {e}")

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
    print(f"--- Verificando: {datetime.datetime.now().strftime('%H:%M:%S')} ---")
    
    try:
        # Configuração SSL
        ctx = ssl.create_default_context()
        ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, ssl_context=ctx)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("INBOX")
        
        # Busca APENAS NÃO LIDOS
        status, messages = mail.search(None, 'UNSEEN')
        email_ids = messages[0].split()
        
        if not email_ids:
            print(" > Nenhum e-mail novo.")
            return # Sai da função se não tiver nada

        print(f" > Encontrados {len(email_ids)} e-mails. Analisando...")
        
        for e_id in email_ids:
            _, msg_data = mail.fetch(e_id, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            
            assunto = decodificar_texto(msg["Subject"])
            remetente = decodificar_texto(msg["From"]).lower() # Tudo minúsculo
            assunto_upper = assunto.upper().strip()
            
            print(f"   [Analisando] De: {remetente} | Assunto: {assunto}")

            # --- 1. Lógica BIDS ---
            if assunto_upper.startswith("BIDS"):
                mail.store(e_id, '+FLAGS', '\\Deleted')
                print("      [X] DELETE: É um BIDS.")
                continue

            # Extração de Conteúdo
            conteudo_analisado = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try: conteudo_analisado += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        except: pass
                    if "application/pdf" in part.get_content_type() or ".pdf" in str(part.get_filename("")).lower():
                        print("      [PDF] Extraindo texto do anexo...")
                        conteudo_analisado += "\n" + extrair_texto_pdf(part.get_payload(decode=True))
            else:
                try: conteudo_analisado = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                except: pass

            # Busca Palavras
            palavras_encontradas = []
            conteudo_upper = conteudo_analisado.upper()
            for palavra in PALAVRAS_CHAVE:
                if palavra in conteudo_upper:
                    palavras_encontradas.append(palavra)

            if palavras_encontradas:
                print(f"      [!] Palavras encontradas: {palavras_encontradas}")

            # --- 2. Lógica GRÁFICA (BIS) ---
            # Simplificado: Procura "grafica" em qualquer parte do remetente
            if "grafica" in remetente and "BIS" in assunto_upper:
                if palavras_encontradas:
                    enviar_telegram(f"🚨 **SEU NOME NO BIS!**\n{assunto}\nAchou: {palavras_encontradas}")
                else:
                    enviar_telegram(f"ℹ️ **Novo BIS (Sem seu nome)**\n{assunto}")
            
            # --- 3. Lógica DIVPORT ---
            # Simplificado: Procura "divport" em qualquer parte do remetente
            elif "divport" in remetente:
                if palavras_encontradas:
                    enviar_telegram(f"⚠️ **CITAÇÃO NA DIVPORT**\n{assunto}\nAchou: {palavras_encontradas}")
                else:
                    print("      [Divport] Ignorado (sem palavras-chave).")
            
            else:
                print("      [Ignorado] Não é BIS nem DivPort.")

        mail.expunge()
        mail.close()
        mail.logout()
        
    except Exception as e:
        print(f"Erro na execução: {e}")

if __name__ == "__main__":
    # Sem loop infinito. Ele roda uma vez e o GitHub encerra.
    # O agendador do GitHub (CRON) vai chamar de novo daqui a pouco.
    verificar_emails()
