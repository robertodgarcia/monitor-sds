
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
# No GitHub Actions, estas variáveis vêm dos "Secrets".
# Se for rodar no PC para teste, preencha com seus dados reais entre aspas.
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
        response = requests.post(url, data=data)
        if response.status_code != 200:
            print(f" [Erro API Telegram] Status: {response.status_code} | {response.text}")
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

            # Extração de Conteúdo
            conteudo_analisado = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try: conteudo_analisado += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        except: pass
                    if "application/pdf" in part.get_content_type() or ".pdf" in str(part.get_filename("")).lower():
                        print("      [PDF] Lendo anexo...")
                        conteudo_analisado += "\n" + extrair_texto_pdf(part.get_payload(decode=True))
            else:
                try: conteudo_analisado = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                except: pass

            # Lógica de Palavras (Correção 2: Lista direta)
            conteudo_upper = conteudo_analisado.upper()
            palavras_encontradas = [p for p in PALAVRAS_CHAVE if p in conteudo_upper]

            if palavras_encontradas:
                print(f"      [!] Encontrou: {palavras_encontradas}")

            # Lógica GRÁFICA (Correção 1: Checagem simplificada)
            # Verifica se "grafica" está no remetente (não precisa ser o email exato)
            if "grafica" in remetente and "BIS" in assunto_upper:
                if palavras_encontradas:
                    enviar_telegram(f"🚨 **SEU NOME NO BIS!**\n{assunto}\nTermos: {', '.join(palavras_encontradas)}")
                else:
                    enviar_telegram(f"ℹ️ **Novo BIS Publicado**\n{assunto}\n(Nada encontrado)")
            
            # Lógica DIVPORT (Correção 1: Checagem simplificada)
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
    # Correção 3: Teste de Telegram ao iniciar
    # Isso ajuda a saber se o Bot está funcionando toda vez que o GitHub rodar
    print("🤖 Iniciando script via GitHub Actions...")
    enviar_telegram("🤖 Monitor Rodando (GitHub Actions) - Check iniciado.")
    
    # Executa uma vez e encerra (Sem loop, pois é GitHub Actions)
    verificar_emails()
