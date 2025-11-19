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
import re

# --- CONFIGURAÇÕES ---
EMAIL_USER = os.getenv("EMAIL_USER") 
EMAIL_PASS = os.getenv("EMAIL_PASS")
IMAP_SERVER = "imaps.expresso.pe.gov.br"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PALAVRAS_CHAVE = ["DOMINGUEZ", "AGOSTINHO"]

def enviar_telegram(mensagem):
    print(f" [Telegram] Msg: {mensagem[:50]}...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f" [Erro Conexão Telegram] {e}")

def enviar_arquivo_telegram(nome_arquivo, dados_bytes):
    """Envia o arquivo físico (PDF/HTML) para o chat"""
    print(f" [Telegram] Enviando arquivo: {nome_arquivo}...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    
    # Prepara o arquivo para envio via POST
    # A estrutura é {'document': (nome_que_vai_aparecer, dados_binarios)}
    files = {'document': (nome_arquivo, dados_bytes)}
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": f"📎 Anexo: {nome_arquivo}"}
    
    try:
        r = requests.post(url, data=data, files=files)
        if r.status_code != 200:
            print(f"Erro envio arquivo: {r.text}")
    except Exception as e:
        print(f" [Erro Envio Arquivo] {e}")

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
    try:
        texto_html = payload_bytes.decode('utf-8', errors='ignore')
        clean = re.compile('<.*?>')
        return re.sub(clean, ' ', texto_html)
    except:
        return ""

def decodificar_texto(header_text):
    if not header_text: return ""
    decoded_list = decode_header(header_text)
    texto_final = ""
    for content, encoding in decoded_list:
        if isinstance(content, bytes):
            try: texto_final += content.decode(encoding or 'utf-8', errors='ignore')
            except: texto_final += content.decode('utf-8', errors='ignore')
        else:
            texto_final += str(content)
    return texto_final

def verificar_emails():
    print(f"--- Iniciando verificação: {datetime.datetime.now()} ---")
    
    if not EMAIL_USER or not EMAIL_PASS:
        print("ERRO CRÍTICO: Credenciais não encontradas.")
        return

    try:
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers('DEFAULT@SECLEVEL=1')
        
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, ssl_context=ssl_context)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("INBOX")
        
        # Busca APENAS e-mails novos
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
            
            print(f"   Checando: {assunto}")

            if assunto_upper.startswith("BIDS"):
                mail.store(e_id, '+FLAGS', '\\Deleted')
                print("   -> BIDS deletado.")
                continue

            # Variáveis para guardar o que vamos enviar
            conteudo_analisado = ""
            anexos_para_enviar = [] # Lista para guardar (nome, bytes)

            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    filename = part.get_filename()
                    if filename: filename = decodificar_texto(filename)
                    else: filename = "anexo_sem_nome"

                    payload = part.get_payload(decode=True)
                    if not payload: continue

                    # 1. Texto Simples
                    if ctype == "text/plain":
                        try: conteudo_analisado += payload.decode('utf-8', errors='ignore')
                        except: pass
                    
                    # 2. PDF
                    elif "application/pdf" in ctype or ".pdf" in filename.lower():
                        print("      [PDF] Processando...")
                        conteudo_analisado += "\n" + extrair_texto_pdf(payload)
                        # Guarda o arquivo na memória para enviar se precisar
                        anexos_para_enviar.append( (filename, payload) )
                    
                    # 3. HTML
                    elif "html" in ctype or ".html" in filename.lower() or ".htm" in filename.lower():
                        print("      [HTML] Processando...")
                        conteudo_analisado += "\n" + extrair_texto_html(payload)
                        # Se o arquivo não tiver nome (comum em corpo de email), dá um nome
                        if filename == "anexo_sem_nome": filename = "conteudo_email.html"
                        anexos_para_enviar.append( (filename, payload) )

            else:
                # Email sem anexo (Corpo puro)
                ctype = msg.get_content_type()
                payload = msg.get_payload(decode=True)
                if "html" in ctype:
                     conteudo_analisado = extrair_texto_html(payload)
                     # Guarda o corpo como arquivo HTML
                     anexos_para_enviar.append( ("corpo_email.html", payload) )
                else:
                     try: conteudo_analisado = payload.decode('utf-8', errors='ignore')
                     except: pass

            # Analisa Palavras
            conteudo_upper = conteudo_analisado.upper()
            palavras_encontradas = [p for p in PALAVRAS_CHAVE if p in conteudo_upper]

            if palavras_encontradas:
                print(f"      [!] ACHOU: {palavras_encontradas}")

            # --- DISPARO DE ALERTAS ---
            
            deve_enviar_arquivo = False

            # Lógica BIS
            if "grafica" in remetente and "BIS" in assunto_upper:
                if palavras_encontradas:
                    enviar_telegram(f"🚨 **SEU NOME NO BIS!**\n{assunto}\nTermos: {', '.join(palavras_encontradas)}")
                    deve_enviar_arquivo = True
                else:
                    enviar_telegram(f"ℹ️ **Novo BIS Publicado**\n{assunto}\n(Nada encontrado)")
            
            # Lógica DIVPORT
            elif "divport" in remetente:
                if palavras_encontradas:
                    enviar_telegram(f"⚠️ **CITAÇÃO NA DIVPORT**\n{assunto}\nTermos: {', '.join(palavras_encontradas)}")
                    deve_enviar_arquivo = True

            # --- ENVIO DOS ARQUIVOS ---
            if deve_enviar_arquivo and anexos_para_enviar:
                enviar_telegram("📎 Enviando documentos encontrados...")
                for nome, dados in anexos_para_enviar:
                    enviar_arquivo_telegram(nome, dados)

        mail.expunge()
        mail.close()
        mail.logout()
        
    except Exception as e:
        print(f"Erro na execução: {e}")

if __name__ == "__main__":
    # Teste ao iniciar
    print("🤖 Script Iniciado...")
    enviar_telegram("🤖 Monitor v4.0 (Com envio de arquivos) - Check.")
    verificar_emails()
