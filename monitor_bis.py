def verificar_emails():
    # ... (Inicializações omitidas)

    try:
        # ... (Conexão e busca de emails omitidas)
        
        email_ids = messages[0].split()
        
        total_emails_encontrados = len(email_ids)
        
        # --- NOVO RELATÓRIO: Variáveis de Contagem Específicas ---
        # Contadores de emails onde CADA palavra-chave foi encontrada
        qtd_com_agostinho = 0
        qtd_com_dominguez = 0
        
        emails_nao_bids_processados = 0 
        
        if not email_ids:
            print(" > Nenhum e-mail novo.")
            return
            
        print(f" > Encontrados {total_emails_encontrados} novos e-mails.")

        for e_id in email_ids:
            # ... (Busca do e-mail e checagem BIDS omitidas)

            # --- CORREÇÃO: Variáveis de flag por email ---
            achou_agostinho_no_email = False
            achou_dominguez_no_email = False
            
            anexos_encontrados = [] # Armazena todos os anexos para a próxima etapa (corpo do email não entra)
            
            # --- PROCESSAMENTO ---
            if msg.is_multipart():
                for part in msg.walk():
                    # ... (código de identificação de anexo/conteúdo omitido)
                    
                    if "application/pdf" in ctype or ".pdf" in filename.lower():
                        conteudo_anexo = extrair_texto_pdf(payload)
                        conteudo_analisado += "\n" + conteudo_anexo
                        anexos_encontrados.append((filename, payload, conteudo_anexo)) # Armazena anexo e o texto extraído
                        
                    elif "html" in ctype or ".html" in filename.lower():
                        conteudo_anexo = extrair_texto_html(payload)
                        conteudo_analisado += "\n" + conteudo_anexo
                        if not filename.lower().endswith(".html"): filename += ".html"
                        anexos_encontrados.append((filename, payload, conteudo_anexo)) # Armazena anexo e o texto extraído

                    elif "text/plain" in ctype:
                        try: conteudo_analisado += payload.decode('utf-8', errors='ignore')
                        except: pass
            else:
                # ... (processamento de email não-multipart omitido, adicionado à lista para checagem)
                ctype = msg.get_content_type()
                payload = msg.get_payload(decode=True)
                if "html" in ctype:
                    conteudo_analisado = extrair_texto_html(payload)
                    anexos_encontrados.append(("email_completo.html", payload, conteudo_analisado))
                else:
                    try: conteudo_analisado = payload.decode('utf-8', errors='ignore')
                    except: pass
                    
            # --- VERIFICAÇÃO GERAL NO EMAIL (Corpo + Anexos) ---
            conteudo_upper = conteudo_analisado.upper()
            palavras_encontradas = [p for p in PALAVRAS_CHAVE if p in conteudo_upper]
            
            if "AGOSTINHO" in conteudo_upper:
                achou_agostinho_no_email = True
            if "DOMINGUEZ" in conteudo_upper:
                achou_dominguez_no_email = True
                
            deve_enviar_arquivo = False
            alerta_gerado = False
            
            # ... (Lógica GRÁFICA e DIVPORT omitida)

            # --- CORREÇÃO DE CONTAGEM ---
            if alerta_gerado:
                if achou_agostinho_no_email:
                    qtd_com_agostinho += 1
                if achou_dominguez_no_email:
                    qtd_com_dominguez += 1
            # O contador qtd_com_alerta e qtd_sem_alerta não serão mais usados no relatório final, 
            # mas podem ser mantidos para a lógica de 'alerta_gerado'.

            # --- CORREÇÃO DE ENVIO DOS ARQUIVOS ---
            if deve_enviar_arquivo:
                enviado_com_sucesso = False
                
                # 1. Tenta encontrar a palavra-chave no anexo (só em PDF/HTML/TEXTO)
                for nome, dados, texto_anexo in anexos_encontrados:
                    texto_anexo_upper = texto_anexo.upper()
                    
                    # Checa se o anexo tem alguma das palavras-chave
                    if any(p in texto_anexo_upper for p in PALAVRAS_CHAVE):
                        enviar_arquivo_telegram(nome, dados)
                        enviado_com_sucesso = True
                        break # CORREÇÃO: Envia o primeiro anexo que contém a palavra-chave e PARA!
                        
                # 2. Caso nenhum anexo legível/compatível tenha a palavra, mas o corpo do email sim (alerta_gerado=True)
                if not anexos_encontrados:
                    enviar_telegram("⚠️ Encontrei a palavra-chave no corpo do e-mail, mas não havia anexo legível para envio.")

            # ... (Loop continua)
            
        # --- NOVO RELATÓRIO FINAL ---
        if emails_nao_bids_processados > 0:
            
            # Cálculo dos "sem palavra-chave"
            qtd_sem_agostinho = emails_nao_bids_processados - qtd_com_agostinho
            qtd_sem_dominguez = emails_nao_bids_processados - qtd_com_dominguez
            
            relatorio = (
                f"📊 **relatorio final**\n"
                f"📨 Processados: {emails_nao_bids_processados}\n"
                f"com palavra chave agostinho: **{qtd_com_agostinho}**\n"
                f"com palavra chave dominguez: **{qtd_com_dominguez}**\n"
                f"\n"
                f"sem palavra chave agostinho: {qtd_sem_agostinho}\n"
                f"sem palavra chave dominguez: {qtd_sem_dominguez}"
            )
            enviar_telegram(relatorio)

        # ... (Finalização da conexão omitida)
