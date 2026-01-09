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

# --- CONFIGURAÇÕES (Variáveis Globais) ---
# Estas variáveis buscam os Secrets definidos no GitHub Actions.
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
IMAP_SERVER = "imaps.expresso.pe.gov.br"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PALAVRAS_CHAVE = ["DOMINGUEZ", "AGOSTINHO"]
# --- FIM CONFIGURAÇÕES ---

# --- FUNÇÕES AUXILIARES ---

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

# --- FUNÇÃO PRINCIPAL ---

def verificar_emails():
    print(f"--- Iniciando verificação: {datetime.datetime.now()} ---")
    
    # 1. Checagem de Variáveis Globais (Solução para NameError)
    if not EMAIL_USER or not EMAIL_PASS:
        print("ERRO: Secrets não configurados. EMAIL_USER ou EMAIL_PASS está vazio.")
        return

    try:
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers('DEFAULT@SECLEVEL=1')
        
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, ssl_context=ssl_context)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("INBOX")
        
        status, messages = mail.search(None, 'UNSEEN')
        email_ids = messages[0].split()
        
        total_emails_encontrados = len(email_ids)
        
        # --- Variáveis de Contagem Global ---
        emails_nao_bids_processados = 0
        qtd_com_agostinho = 0
        qtd_com_dominguez = 0
        qtd_anexos_com_alerta = 0
        qtd_anexos_sem_alerta = 0
        
        if not email_ids:
            print(" > Nenhum e-mail novo.")
            return
            
        print(f" > Encontrados {total_emails_encontrados} novos e-mails.")
        enviar_telegram(f"🔄 Verificando {total_emails_encontrados} novos e-mails...")
        
        for e_id in email_ids:
            _, msg_data = mail.fetch(e_id, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            
            assunto = decodificar_texto(msg["Subject"])
            remetente = decodificar_texto(msg["From"]).lower()
            assunto_upper = assunto.upper().strip()
            
            print(f"    Checando: {assunto}")

            if assunto_upper.startswith("BIDS"):
                mail.store(e_id, '+FLAGS', '\\Deleted')
                continue
            
            emails_nao_bids_processados += 1
            
            # Variáveis locais por e-mail
            achou_agostinho_no_email = False
            achou_dominguez_no_email = False
            conteudo_analisado = ""
            anexos_encontrados = [] # Armazena (nome, payload, conteudo_anexo)
            
            # --- PROCESSAMENTO DOS ANEXOS E CONTEÚDO ---
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    filename = part.get_filename()
                    if filename: filename = decodificar_texto(filename)
                    else:
                        if "pdf" in ctype: filename = "documento.pdf"
                        elif "html" in ctype: filename = "corpo_email.html"
                        else: continue

                    payload = part.get_payload(decode=True)
                    if not payload: continue
                    
                    conteudo_anexo = ""

                    if "application/pdf" in ctype or ".pdf" in filename.lower():
                        conteudo_anexo = extrair_texto_pdf(payload)
                        anexos_encontrados.append((filename, payload, conteudo_anexo))
                    
                    elif "html" in ctype or ".html" in filename.lower():
                        conteudo_anexo = extrair_texto_html(payload)
                        if not filename.lower().endswith(".html"): filename += ".html"
                        anexos_encontrados.append((filename, payload, conteudo_anexo))
                        
                    elif "text/plain" in ctype:
                        try: conteudo_analisado += payload.decode('utf-8', errors='ignore')
                        except: pass
                        continue # Não conta 'text/plain' como anexo individual
                    
                    conteudo_analisado += "\n" + conteudo_anexo

            else: # E-mail não-multipart (corpo único)
                # Lógica para tratar e-mail como um único "anexo" (HTML/Texto)
                ctype = msg.get_content_type()
                payload = msg.get_payload(decode=True)
                conteudo_anexo = ""
                
                if "html" in ctype:
                    conteudo_anexo = extrair_texto_html(payload)
                    anexos_encontrados.append(("email_completo.html", payload, conteudo_anexo))
                else:
                    try: conteudo_anexo = payload.decode('utf-8', errors='ignore')
                    except: pass
                    
                conteudo_analisado = conteudo_anexo

            # --- LÓGICA DE ALERTA ---
            conteudo_upper = conteudo_analisado.upper()
            palavras_encontradas = [p for p in PALAVRAS_CHAVE if p in conteudo_upper]
            
            deve_enviar_arquivo = False
            alerta_gerado = False

            # 1. GRÁFICA / 2. DIVPORT
            if ("grafica" in remetente and "BIS" in assunto_upper) or ("divport" in remetente):
                if palavras_encontradas:
                    alerta_tipo = "🚨 **SEU NOME NO BIS!**" if "grafica" in remetente else "⚠️ **CITAÇÃO NA DIVPORT**"
                    enviar_telegram(f"{alerta_tipo}\n{assunto}\nTermos: {palavras_encontradas}")
                    deve_enviar_arquivo = True
                    alerta_gerado = True
                elif "grafica" in remetente:
                    enviar_telegram(f"ℹ️ **Novo BIS Publicado**\n{assunto}\n(Nada encontrado)")

            # --- CONTAGEM DE EMAILS ---
            if alerta_gerado:
                if "AGOSTINHO" in conteudo_upper:
                    qtd_com_agostinho += 1
                if "DOMINGUEZ" in conteudo_upper:
                    qtd_com_dominguez += 1

            # --- ENVIO E CONTAGEM DOS ANEXOS (CORREÇÃO DE MÚLTIPLOS ENVIOS E CONTAGEM) ---
            
            if deve_enviar_arquivo:
                
                # Tenta encontrar a palavra-chave no anexo
                for nome, dados, texto_anexo in anexos_encontrados:
                    texto_anexo_upper = texto_anexo.upper()
                    
                    if any(p in texto_anexo_upper for p in PALAVRAS_CHAVE):
                        enviar_arquivo_telegram(nome, dados)
                        qtd_anexos_com_alerta += 1 # Conta como anexo COM palavra-chave
                    else:
                        qtd_anexos_sem_alerta += 1 # Conta como anexo SEM palavra-chave
                        
                # Se o alerta foi gerado, mas a lista de anexos está vazia/não processável
                if not anexos_encontrados:
                    enviar_telegram("⚠️ Alerta gerado no corpo do e-mail, mas não havia anexo legível para envio.")

            # Se o alerta NÃO foi gerado, e existem anexos, todos são contados como "sem palavra chave"
            elif len(anexos_encontrados) > 0:
                qtd_anexos_sem_alerta += len(anexos_encontrados)

        # --- RELATÓRIO FINAL ---
        if emails_nao_bids_processados > 0:
            
            # Cálculo dos "sem palavra-chave" no email
            qtd_sem_agostinho = emails_nao_bids_processados - qtd_com_agostinho
            qtd_sem_dominguez = emails_nao_bids_processados - qtd_com_dominguez
            
            total_anexos_processados = qtd_anexos_com_alerta + qtd_anexos_sem_alerta
            
            relatorio = (
                f"📊 **relatorio final**\n"
                f"\n"
                f"**Métricas por Email:**\n"
                f"Emails Processados: {emails_nao_bids_processados}\n"
                f"com palavra chave agostinho: **{qtd_com_agostinho}**\n"
                f"com palavra chave dominguez: **{qtd_com_dominguez}**\n"
                f"sem palavra chave agostinho: {qtd_sem_agostinho}\n"
                f"sem palavra chave dominguez: {qtd_sem_dominguez}\n"
                f"\n"
                f"**Métricas por Anexo:**\n"
                f"Anexos Processados: {total_anexos_processados}\n"
                f"Anexos com palavra chave: **{qtd_anexos_com_alerta}**\n"
                f"Anexos sem palavra chave: {qtd_anexos_sem_alerta}"
            )
            enviar_telegram(relatorio)

        mail.expunge()
        mail.close()
        mail.logout()
        
    except Exception as e:
        print(f"Erro na execução: {e}")
        enviar_telegram(f"⚠️ Erro no script: {e}")

if __name__ == "__main__":
    print("🤖 Monitor v7.2 (Completo e Estruturado)...")
    verificar_emails()
