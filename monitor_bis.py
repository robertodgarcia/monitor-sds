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
    print(f" [Telegram] UPLOAD iniciando: {nome_arquivo}...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    
    if "html" in nome_arquivo.lower() and not nome_arquivo.lower().endswith(".html"):
        nome_arquivo += ".html"

    files = {'document': (nome_arquivo, dados_bytes)}
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": f"📎 Anexo: {nome_arquivo}"}
    
    try:
        r = requests.post(url, data=data, files=files)
        if r.status_code != 200:
            enviar_telegram(f"⚠️ Erro ao enviar arquivo {nome_arquivo}")
    except Exception as e:
        print(f" [Erro Crítico Envio] {e}")

def extrair_texto_pdf(payload_bytes):
    texto_completo = ""
    try:
        arquivo_pdf = io.BytesIO(payload_bytes)
        leitor = PyPDF2.PdfReader(arquivo_pdf)
        for pagina in leitor.pages:
            texto_completo += pagina.extract_text() + "\n"
    except: return ""
    return texto_completo

def extrair_texto_html(payload_bytes):
    try:
        texto_html = payload_bytes.decode('utf-8', errors='ignore')
        clean = re.compile('<.*?>')
        return re.sub(clean, ' ', texto_html)
    except: return ""

def decodificar_texto(header_text):
    if not header_text: return ""
    decoded_list = decode_header(header_text)
    texto_final = ""
    for content, encoding in decoded_list:
        if isinstance(content, bytes):
            try: texto_final += content.decode(encoding or 'utf-8', errors='ignore')
            except: texto_final += content.decode('utf-8', errors='ignore')
        else: texto_final += str(content)
    return texto_final

def verificar_emails():
    print(f"--- Iniciando verificação: {datetime.datetime.now()} ---")
    
    if not EMAIL_USER or not EMAIL_PASS:
        print("ERRO: Secrets não configurados.")
        return

    try:
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers('DEFAULT@SECLEVEL=1')
        
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, ssl_context=ssl_context)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("INBOX")
        
        status, messages = mail.search(None, 'UNSEEN')
        email_ids = messages[0].split()
        
        total_emails = len(email_ids)
        qtd_com_alerta = 0
        qtd_sem_alerta = 0

        if not email_ids:
            print(" > Nenhum e-mail novo.")
            enviar_telegram(f"📊 **Relatório de Check:**\nNenhum e-mail novo encontrado.")
            return
        
        print(f" > Encontrados {total_emails} novos e-mails.")
        enviar_telegram(f"🔄 Verificando {total_emails} novos e-mails...")

        for e_id in email_ids:
            _, msg_data = mail.fetch(e_id, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            
            assunto = decodificar_texto(msg["Subject"])
            remetente = decodificar_texto(msg["From"]).lower()
            assunto_upper = assunto.upper().strip()
            
            print(f"   Checando: {assunto}")

            if assunto_upper.startswith("BIDS"):
                mail.store(e_id, '+FLAGS', '\\Deleted')
                total_emails -= 1 
                continue

            conteudo_analisado = ""
            
            # Listas separadas para fazer a filtragem depois
            lista_pdfs = []
            lista_htmls = []

            # --- PROCESSAMENTO ---
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    filename = part.get_filename()
                    if filename: filename = decodificar_texto(filename)
                    else:
                        if "pdf" in ctype: filename = "documento.pdf"
                        elif "html" in ctype: filename = "corpo_email.html"
                        else: filename = "anexo.txt"

                    payload = part.get_payload(decode=True)
                    if not payload: continue

                    if "application/pdf" in ctype or ".pdf" in filename.lower():
                        conteudo_analisado += "\n" + extrair_texto_pdf(payload)
                        lista_pdfs.append((filename, payload))
                    
                    elif "html" in ctype or ".html" in filename.lower():
                        conteudo_analisado += "\n" + extrair_texto_html(payload)
                        if not filename.lower().endswith(".html"): filename += ".html"
                        lista_htmls.append((filename, payload))

                    elif "text/plain" in ctype:
                        try: conteudo_analisado += payload.decode('utf-8', errors='ignore')
                        except: pass
            else:
                ctype = msg.get_content_type()
                payload = msg.get_payload(decode=True)
                if "html" in ctype:
                     conteudo_analisado = extrair_texto_html(payload)
                     lista_htmls.append(("email_completo.html", payload))
                else:
                     try: conteudo_analisado = payload.decode('utf-8', errors='ignore')
                     except: pass

            # --- LÓGICA DE PRIORIDADE DE ANEXO ---
            # Se tiver PDF, manda SÓ os PDFs. Se não tiver, manda os HTMLs.
            anexos_para_enviar = []
            if lista_pdfs:
                anexos_para_enviar = lista_pdfs
            else:
                anexos_para_enviar = lista_htmls

            # --- VERIFICAÇÃO ---
            conteudo_upper = conteudo_analisado.upper()
            palavras_encontradas = [p for p in PALAVRAS_CHAVE if p in conteudo_upper]
            
            deve_enviar_arquivo = False
            alerta_gerado = False

            # 1. GRÁFICA
            if "grafica" in remetente and "BIS" in assunto_upper:
                if palavras_encontradas:
                    enviar_telegram(f"🚨 **SEU NOME NO BIS!**\n{assunto}\nTermos: {palavras_encontradas}")
                    deve_enviar_arquivo = True
                    alerta_gerado = True
                else:
                    enviar_telegram(f"ℹ️ **Novo BIS Publicado**\n{assunto}\n(Nada encontrado)")

            # 2. DIVPORT
            elif "divport" in remetente:
                if palavras_encontradas:
                    enviar_telegram(f"⚠️ **CITAÇÃO NA DIVPORT**\n{assunto}\nTermos: {palavras_encontradas}")
                    deve_enviar_arquivo = True
                    alerta_gerado = True

            if alerta_gerado:
                qtd_com_alerta += 1
            else:
                qtd_sem_alerta += 1

            # --- ENVIO DOS ARQUIVOS ---
            if deve_enviar_arquivo:
                if anexos_para_enviar:
                    for nome, dados in anexos_para_enviar:
                        enviar_arquivo_telegram(nome, dados)
                else:
                    # Se chegou aqui e não tem anexo nenhum (nem PDF nem HTML)
                    enviar_telegram("⚠️ Encontrei o nome, mas não havia anexo legível.")

        # --- RELATÓRIO FINAL ---
        relatorio = (
            f"📊 **Relatório Final:**\n"
            f"📨 Processados: {total_emails}\n"
            f"🚨 Com seu nome: {qtd_com_alerta}\n"
            f"⚪ Sem seu nome: {qtd_sem_alerta}"
        )
        enviar_telegram(relatorio)

        mail.expunge()
        mail.close()
        mail.logout()
        
    except Exception as e:
        print(f"Erro na execução: {e}")
        enviar_telegram(f"⚠️ Erro no script: {e}")

if __name__ == "__main__":
    print("🤖 Monitor v7.0 (Prioridade PDF)...")
    verificar_emails()
