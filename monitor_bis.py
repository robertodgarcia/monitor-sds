import imaplib
import email
from email.header import decode_header
import time
import requests
import io
import PyPDF2
import os
import datetime
import ssl # <--- Essencial para corrigir o erro de chave

# --- CONFIGURAÇÕES ---
# Se estiver rodando localmente/VPS e as variáveis não estiverem setadas, 
# substitua os os.getenv pelo valor real entre aspas.
EMAIL_USER = os.getenv("EMAIL_USER") 
EMAIL_PASS = os.getenv("EMAIL_PASS")
IMAP_SERVER = "imaps.expresso.pe.gov.br"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PALAVRAS_CHAVE = ["DOMINGUEZ", "AGOSTINHO"]

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Erro Telegram: {e}")

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
    print(f"--- Iniciando verificação: {datetime.datetime.now()} ---")
    
    # Verifica se as senhas existem antes de tentar
    if not EMAIL_USER or not EMAIL_PASS:
        print("ERRO CRÍTICO: Variáveis de ambiente (EMAIL_USER/PASS) não encontradas.")
        print("Se estiver rodando no PC/VPS, preencha as variáveis no topo do script.")
        return

    try:
        # --- CORREÇÃO DO ERRO DH KEY TOO SMALL ---
        # Criamos um contexto SSL que aceita criptografia mais antiga (SECLEVEL=1)
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers('DEFAULT@SECLEVEL=1')
        
        # Conectamos ao servidor usando esse contexto
        print("Conectando ao servidor...")
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, ssl_context=ssl_context)
        
        # Login
        mail.login(EMAIL_USER, EMAIL_PASS)
        print("Login realizado com sucesso.")
        # -----------------------------------------

        mail.select("INBOX")
        
        status, messages = mail.search(None, 'UNSEEN')
        email_ids = messages[0].split()
        
        if not email_ids:
            print("Nenhum e-mail novo.")
        
        for e_id in email_ids:
            _, msg_data = mail.fetch(e_id, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            
            assunto = decodificar_texto(msg["Subject"])
            remetente = decodificar_texto(msg["From"]).lower()
            assunto_upper = assunto.upper().strip()
            
            print(f"Checando: {assunto}")

            # Lógica BIDS (Apagar)
            if assunto_upper.startswith("BIDS"):
                mail.store(e_id, '+FLAGS', '\\Deleted')
                print(" -> BIDS deletado.")
                continue

            encontrou_palavra = False
            palavras_encontradas = []
            conteudo_analisado = ""

            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try: conteudo_analisado += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        except: pass
                    if "application/pdf" in part.get_content_type() or ".pdf" in str(part.get_filename("")).lower():
                        conteudo_analisado += "\n" + extrair_texto_pdf(part.get_payload(decode=True))
            else:
                try: conteudo_analisado = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                except: pass

            conteudo_upper = conteudo_analisado.upper()
            for palavra in PALAVRAS_CHAVE:
                if palavra in conteudo_upper:
                    encontrou_palavra = True
                    palavras_encontradas.append(palavra)

            if "grafica@policiacivil.pe.gov.br" in remetente and assunto_upper.startswith("BIS"):
                if encontrou_palavra:
                    enviar_telegram(f"🚨 **SEU NOME NO BIS!**\n{assunto}\nTermos: {', '.join(palavras_encontradas)}")
                else:
                    enviar_telegram(f"ℹ️ **Novo BIS Publicado**\n{assunto}\n(Nada encontrado)")
            
            elif "divport@policiacivil.pe.gov.br" in remetente and encontrou_palavra:
                enviar_telegram(f"⚠️ **CITAÇÃO NA DIVPORT**\n{assunto}\nTermos: {', '.join(palavras_encontradas)}")

        mail.expunge()
        mail.close()
        mail.logout()
        
    except Exception as e:
        print(f"Erro na execução: {e}")

if __name__ == "__main__":
    # Se for rodar na VPS para sempre, descomente as linhas abaixo e comente a verificar_emails() sozinha
    # while True:
    #     verificar_emails()
    #     time.sleep(300)
    
    verificar_emails()
