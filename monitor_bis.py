import imaplib
import email
from email.header import decode_header
import time
import requests
import io
import PyPDF2
import os
import datetime # Certifique-se de que está aqui!
import ssl
import re

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
        
        total_emails_encontrados = len(email_ids)
        
        # --- NOVO RELATÓRIO: Variáveis de Contagem (Geral e Email) ---
        emails_nao_bids_processados = 0
        qtd_com_agostinho = 0
        qtd_com_dominguez = 0
        
        # --- NOVO RELATÓRIO: Variáveis de Contagem (Anexos) ---
        qtd_anexos_com_alerta = 0
        qtd_anexos_sem_alerta = 0
        
        if not email_ids:
            print(" > Nenhum e-mail novo.")
            return
            
        print(f" > Encontrados {total_emails_encontrados} novos e-mails.")
        
        # Envia a notificação inicial fora do loop, pois a filtragem BIDS pode diminuir a contagem.
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
            
            # Variáveis locais por e-mail para contagem e envio
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
                        # Atribui um nome para anexos sem nome
                        if "pdf" in ctype: filename = "documento.pdf"
                        elif "html" in ctype: filename = "corpo_email.html"
                        else: continue # Ignora partes sem nome e sem tipo relevante

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
                        continue # Não conta 'text/plain' como anexo individual, apenas corpo
                    
                    # Adiciona o texto extraído do anexo ao conteúdo geral
                    conteudo_analisado += "\n" + conteudo_anexo

            else: # E-mail não-multipart (corpo único)
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

            # --- VERIFICAÇÃO GERAL NO EMAIL (Corpo + Anexos) ---
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

            # --- CONTAGEM DE EMAILS ---
            if "AGOSTINHO" in conteudo_upper:
                achou_agostinho_no_email = True
            if "DOMINGUEZ" in conteudo_upper:
                achou_dominguez_no_email = True

            if alerta_gerado:
                if achou_agostinho_no_email:
                    qtd_com_agostinho += 1
                if achou_dominguez_no_email:
                    qtd_com_dominguez += 1

            # --- ENVIO E CONTAGEM DOS ANEXOS (CORRIGIDO) ---
            
            # Anexos enviados com sucesso para o Telegram
            total_anexos_enviados_neste_email = 0
            
            if deve_enviar_arquivo:
                
                # Tenta encontrar a palavra-chave no anexo
                for nome, dados, texto_anexo in anexos_encontrados:
                    texto_anexo_upper = texto_anexo.upper()
                    
                    # Checa se o anexo tem alguma das palavras-chave
                    if any(p in texto_anexo_upper for p in PALAVRAS_CHAVE):
                        enviar_arquivo_telegram(nome, dados)
                        qtd_anexos_com_alerta += 1 # Incrementa contador GLOBAL de ANEXOS COM
                        total_anexos_enviados_neste_email += 1
                    else:
                        # Se não tinha a palavra, conta como ANEXO SEM (dentro de um email com alerta)
                        qtd_anexos_sem_alerta += 1

                # Caso o alerta tenha sido gerado, mas não havia anexos legíveis
                if not anexos_encontrados:
                    enviar_telegram("⚠️ Encontrei a palavra-chave no corpo do e-mail, mas não havia anexo legível para envio.")

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
    print("🤖 Monitor v7.1 (Prioridade PDF/Contagem Anexos)...")
    verificar_emails()
