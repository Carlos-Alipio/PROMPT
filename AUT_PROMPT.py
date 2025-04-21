# -*- coding: utf-8 -*-
"""
Aplicação Streamlit para gerar conteúdo educacional com a API Gemini,
permitindo upload de arquivos PDF e TXT como referência e exportação
para Microsoft Word (.docx).
"""

# --- Importações de Bibliotecas ---
import streamlit as st
import textwrap
import requests
import json
import os
from docx import Document
from io import BytesIO
import fitz  # PyMuPDF - usado para ler PDFs
import time

# ==============================================================================
# == SEÇÃO: FUNÇÕES AUXILIARES
# ==============================================================================
# Estas funções realizam tarefas específicas e são chamadas pela interface.

# --- 1. Configuração da API Key ---
# Lê a chave da API do ambiente. Lembre-se de definir GEMINI_API_KEY!
# API_KEY = os.environ.get("GEMINI_API_KEY")
# Alternativa usando Streamlit Secrets (recomendado):
API_KEY = st.secrets.get("GEMINI_API_KEY")


# --- 2. Extração de Texto de Arquivos ---
def extract_text_from_uploaded_file(uploaded_file):
    """
    Extrai texto de arquivos .txt ou .pdf enviados via Streamlit.

    Parâmetros:
        uploaded_file: Objeto de arquivo carregado pelo st.file_uploader.

    Retorna:
        str: O texto extraído do arquivo, ou None se ocorrer um erro
             ou o tipo de arquivo não for suportado.
    """
    if uploaded_file is None:
        return None

    file_name = uploaded_file.name
    file_type = uploaded_file.type
    # Lê os bytes do arquivo em memória para processamento
    file_bytes = BytesIO(uploaded_file.getvalue())

    extracted_text = ""

    try:
        if file_type == "application/pdf":
            # Usa PyMuPDF (fitz) para processar PDF
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                # Itera por todas as páginas do PDF
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    extracted_text += page.get_text("text") # Extrai texto simples
            st.info(f"Texto extraído de '{file_name}' (PDF).") # Feedback na interface
            return extracted_text

        elif file_type == "text/plain":
            # Processa arquivo de texto simples (TXT)
            string_data = file_bytes.read().decode("utf-8") # Decodifica bytes para string UTF-8
            st.info(f"Texto extraído de '{file_name}' (TXT).") # Feedback na interface
            return string_data
        else:
            # Alerta se o tipo de arquivo não for .txt ou .pdf
            st.warning(f"Tipo de arquivo '{file_type}' não suportado para '{file_name}'. Processando apenas .txt e .pdf.")
            return None

    except Exception as e:
        # Exibe erro se algo falhar durante a leitura do arquivo
        st.error(f"Erro ao processar o arquivo '{file_name}': {e}")
        return None

# --- 3. Geração do Prompt para a API ---
# Função generate_prompt MODIFICADA para evitar tópicos:
def generate_prompt(topic, section_titles, detailed_instructions, file_content=None):
    """
    Monta o prompt final a ser enviado para a API Gemini,
    incorporando o tópico, seções, instruções e o conteúdo
    extraído dos arquivos de referência. INCLUI INSTRUÇÃO PARA EVITAR TÓPICOS.

    Parâmetros:
        topic (str): Tópico principal.
        section_titles (list): Lista com os títulos das seções.
        detailed_instructions (str): Instruções adicionais.
        file_content (str, opcional): Texto combinado extraído dos arquivos.

    Retorna:
        str: O prompt formatado.
    """
    prompt_base = f"""
    Atue como um professor experiente em Educação, especializado em {topic} para a avaliação na aprendizagem. Você deverá elaborar um texto objetivo e didático,
    que será utilizado como uma unidade de aprendizagem em uma apostila de um curso de graduação na área de Tecnologias Educacionais na avaliação educacional.

    **IMPORTANTE:** Elabore o texto completo em **formato de prosa contínua**, utilizando parágrafos bem estruturados. **Evite o uso de marcadores (bullet points), numeração excessiva ou formatação em tópicos**, exceto quando estritamente necessário para listar exemplos de ferramentas ou links de forma clara e concisa dentro dos parágrafos.

    Esse texto terá uma introdução que contextualiza a importância do planejamento didático para uso das ferramentas digitais adequadas no processo avaliativo
    e se desenvolver depois em {len(section_titles)} subseções com os seguintes subtítulos: {', '.join(section_titles)}

    Para cada subseção você deve elaborar um texto que contextualize o tópico central, caracterize os principais conceitos, cite
    alguns exemplos de boas práticas e metodologias de planejamento didático de processos avaliativos para o uso de tecnologias e
    suas especificidades na educação e indicar alguns links e ferramentas que podem ser utilizadas para apoiar {', '.join(section_titles)},
    bem como a postura do docente diante dos desafios. Identificar questões críticas e possibilidades
    presentes em executar no mundo real cada tópico de cada subseção. Finalize com uma conclusão para cada uma das três subseções.
    Cada subseção deverá ter no máximo duas páginas de Word. Você deve fazer citações e indicar as referências conforme as normas mais
    atuais da ABNT."""

    if detailed_instructions:
        prompt_base += f"\n\nInstruções Adicionais Específicas:\n{detailed_instructions}"

    if file_content:
        prompt_base += f"""

Utilize o seguinte conteúdo extraído dos arquivos fornecidos (.txt, .pdf) como principal referência para embasar suas conceituações e caracterizações, além de outras fontes que julgar pertinentes conforme as normas ABNT:

--- CONTEÚDO DOS ARQUIVOS ---
{file_content}
--- FIM DO CONTEÚDO DOS ARQUIVOS ---
"""
    else:
         prompt_base += "\n\nUtilize as melhores práticas e referências acadêmicas atualizadas para embasar suas conceituações e caracterizações, conforme as normas ABNT."


    prompt_base += """

Ao finalizar, elabore uma conclusão que faça uma síntese do que foi estudado na aula toda, mencionando brevemente o conteúdo principal de
cada subseção. Motive o estudante que continue estudando o tema visando aprimorar futuras formas de avaliação com tecnologias.
Certifique-se de que todas as caracterizações e conceituações sejam embasadas nas referências fornecidas (se houver) e outras fontes ABNT. Lembre-se de manter o formato de prosa contínua, evitando listas ou tópicos.
"""
    return textwrap.dedent(prompt_base)

# --- 4. Chamada à API Gemini ---
def call_gemini(prompt, api_key):
    """
    Envia o prompt para a API Gemini e retorna o texto gerado.

    Parâmetros:
        prompt (str): O prompt completo gerado pela função generate_prompt.
        api_key (str): A chave de API do Gemini.

    Retorna:
        str: O texto gerado pela API, ou uma mensagem de erro, ou None.
    """
    if not api_key:
        # Verifica se a chave foi carregada (útil se st.secrets falhar)
        st.error("Erro: Chave da API do Gemini não encontrada via st.secrets ou variável de ambiente.")
        st.info("Certifique-se de ter um arquivo .streamlit/secrets.toml com GEMINI_API_KEY=\"SUA_CHAVE\" ou a variável de ambiente definida.")
        return None

    api_url_base = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"

    api_url_with_key = f"{api_url_base}?key={api_key}"

    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
         "generationConfig": {
             "temperature": 0.7,
             "maxOutputTokens": 8192
         }
    }

    try:
        response = requests.post(api_url_with_key, headers=headers, json=data, timeout=300)
        response.raise_for_status()
        result_json = response.json()

        if 'candidates' in result_json and result_json['candidates']:
             candidate = result_json['candidates'][0]
             content = candidate.get('content', {})
             parts = content.get('parts', [])
             if parts:
                 return parts[0].get('text', "Nenhum texto encontrado na resposta.")

             finish_reason = candidate.get('finishReason')
             if finish_reason and finish_reason != 'STOP':
                 safety_ratings_info = ""
                 if 'safetyRatings' in candidate:
                     safety_ratings_info = f" Safety Ratings: {candidate['safetyRatings']}"
                 st.warning(f"Geração interrompida. Razão: {finish_reason}.{safety_ratings_info}")
                 return f"Erro: Geração interrompida pela API. Razão: {finish_reason}."
             else:
                  return "Estrutura de resposta inesperada (candidato sem partes)."

        elif 'error' in result_json:
             error_msg = result_json['error'].get('message', 'Erro desconhecido retornado pela API.')
             st.error(f"Erro da API Gemini: {error_msg}")
             return f"Erro da API: {error_msg}"
        else:
             st.error("Nenhum candidato válido retornado pela API. Resposta recebida: " + json.dumps(result_json))
             return "Nenhum candidato válido retornado pela API."

    except requests.exceptions.Timeout:
         st.error("Erro: Tempo limite excedido (timeout) ao chamar a API do Gemini.")
         return None
    except requests.exceptions.RequestException as e:
        error_message = f"Erro na chamada à API do Gemini: {e}"
        if e.response is not None:
            error_message += f"\nStatus Code: {e.response.status_code}"
            try:
                error_details = e.response.json()
                error_message += f"\nDetalhes: {json.dumps(error_details)}"
            except json.JSONDecodeError:
                error_message += f"\nResposta (não JSON): {e.response.text}"
        st.error(error_message)
        return None

# --- 5. Criação do Documento Word ---
def create_word_doc(text):
    """
    Cria um documento Word (.docx) em memória contendo o texto fornecido.

    Parâmetros:
        text (str): O texto a ser inserido no documento.

    Retorna:
        BytesIO: Um buffer de bytes contendo o arquivo .docx.
    """
    document = Document()
    paragraphs = text.split('\n\n')
    for para in paragraphs:
        para_stripped = para.strip()
        if para_stripped:
            document.add_paragraph(para_stripped)

    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer

# ==============================================================================
# == SEÇÃO: INTERFACE GRÁFICA COM STREAMLIT
# ==============================================================================

# --- Configurações Iniciais da Página ---
st.set_page_config(page_title="Gerador de Conteúdo Gemini", layout="wide")
st.title("✍️ Gerador de Conteúdo com Gemini (PDF/TXT)")
st.markdown("""
    **Instruções:**
    1. Preencha as informações sobre o conteúdo (tópico, seções).
    2. Faça o upload de arquivos de referência **(.pdf ou .txt)** que o Gemini deve usar.
    3. Clique em **Gerar Texto e Documento Word**.
    4. Aguarde o processamento e faça o download do arquivo `.docx`.
""")
st.info(f"Executando em: {os.getcwd()} | Hora atual: {time.strftime('%Y-%m-%d %H:%M:%S')}")

# --- Verificação da API Key ---
# Mudança para usar st.secrets como método principal
if not API_KEY:
    st.error("**Atenção:** A variável de ambiente `GEMINI_API_KEY` não foi encontrada via `st.secrets`.")
    st.markdown("""
        Para usar esta aplicação, você precisa configurar a chave da API do Gemini usando o sistema de segredos do Streamlit.
        1. Crie uma pasta chamada `.streamlit` no mesmo diretório deste script (`/Users/carlos/PROMPT/`).
        2. Dentro de `.streamlit`, crie um arquivo chamado `secrets.toml`.
        3. Adicione o seguinte conteúdo ao arquivo `secrets.toml`, substituindo pela sua chave:
           ```toml
           GEMINI_API_KEY = "SUA_CHAVE_AQUI"
           ```
        4. Salve o arquivo e reinicie a aplicação Streamlit (Ctrl+C no terminal e `streamlit run AUT_PROMPT.py` novamente).
    """)
    st.stop()

# --- Layout da Interface (Colunas) ---
col1, col2 = st.columns(2)

# --- Coluna 1: Entradas do Usuário (Texto) ---
with col1:
    st.header("1. Informações do Conteúdo")
    topic = st.text_input("Tópico Principal:", placeholder="Ex: Avaliação Formativa com Ferramentas Digitais")

    if 'num_sections' not in st.session_state:
        st.session_state.num_sections = 3

    st.session_state.num_sections = st.number_input(
        "Número de Seções/Subtítulos:",
        min_value=1, max_value=10, value=st.session_state.num_sections, step=1, key="num_sections_input"
    )

    section_titles = []
    for i in range(st.session_state.num_sections):
        title = st.text_input(f"Título da Seção {i+1}:", key=f"section_{i}", placeholder=f"Ex: Conceitos Chave da Seção {i+1}")
        if title:
            section_titles.append(title.strip())

    detailed_instructions = st.text_area(
        "Instruções Adicionais Específicas (Opcional):", height=150,
        placeholder="Ex: Foque em exemplos práticos para o Ensino Fundamental. Use linguagem acessível."
    )

# --- Coluna 2: Upload de Arquivos ---
with col2:
    st.header("2. Arquivos de Referência")
    uploaded_files = st.file_uploader(
        "Carregar arquivos de referência (.pdf, .txt):", type=['pdf', 'txt'],
        accept_multiple_files=True, key="file_uploader"
    )

    combined_file_content = ""
    if uploaded_files:
        st.write("Arquivos carregados e processados:")
        for uploaded_file in uploaded_files:
            st.write(f"- {uploaded_file.name} ({uploaded_file.type})")
            content = extract_text_from_uploaded_file(uploaded_file)
            if content:
                combined_file_content += f"\n\n--- Conteúdo de {uploaded_file.name} ---\n{content}\n--- Fim de {uploaded_file.name} ---"

# --- Seção 3: Geração e Download ---
st.divider()
st.header("3. Gerar e Baixar")

if 'generated_text' not in st.session_state:
    st.session_state.generated_text = None
if 'prompt_used' not in st.session_state:
    st.session_state.prompt_used = None
if 'word_buffer' not in st.session_state:
    st.session_state.word_buffer = None

if st.button("🚀 Gerar Texto e Documento Word", type="primary", key="generate_button"):
    valid_input = True
    if not topic:
        st.warning("⚠️ Por favor, insira o Tópico Principal.")
        valid_input = False
    if len(section_titles) != st.session_state.num_sections or not all(section_titles):
         st.warning(f"⚠️ Por favor, preencha todos os {st.session_state.num_sections} títulos das seções.")
         valid_input = False
    if uploaded_files and not combined_file_content.strip():
        st.error("❌ Arquivos foram enviados, mas não foi possível extrair conteúdo.")
        valid_input = False

    if valid_input:
        st.session_state.generated_text = None
        st.session_state.prompt_used = None
        st.session_state.word_buffer = None

        with st.spinner("⏳ Processando arquivos, gerando prompt, chamando a API do Gemini e criando o documento..."):
            st.session_state.prompt_used = generate_prompt(
                topic, section_titles, detailed_instructions, combined_file_content
            )
            st.write("✅ Prompt gerado.")
            st.session_state.generated_text = call_gemini(st.session_state.prompt_used, API_KEY)
            st.write("✅ Resposta da API recebida.")

            if st.session_state.generated_text and not st.session_state.generated_text.startswith("Erro:"):
                st.session_state.word_buffer = create_word_doc(st.session_state.generated_text)
                st.write("✅ Documento Word criado.")
                st.success("🎉 Processo concluído com sucesso!")
            elif st.session_state.generated_text:
                 st.error("❌ Falha ao gerar o texto. Verifique a mensagem de erro da API acima.")
            else:
                 st.error("❌ Falha na comunicação com a API ou na criação do documento.")

# --- Exibição dos Resultados ---
if st.session_state.word_buffer:
    st.download_button(
        label="📥 Baixar Documento Word (.docx)",
        data=st.session_state.word_buffer,
        file_name=f"{topic.replace(' ', '_').lower()}_gemini_gerado.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key="download_button"
    )

if st.session_state.prompt_used:
    with st.expander("Ver Prompt Enviado ao Gemini (Pode ser longo com PDFs)"):
        st.text_area("Prompt:", st.session_state.prompt_used, height=300, key="prompt_display")

if st.session_state.generated_text and not st.session_state.generated_text.startswith("Erro:"):
    st.divider()
    st.subheader("Texto Gerado pelo Gemini:")
    st.markdown(st.session_state.generated_text, unsafe_allow_html=False)