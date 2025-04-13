import os
import torch
import whisper
import subprocess
import time
from tqdm import tqdm
from datetime import timedelta, datetime

# ============================== MÉTODOS AUXILIARES ============================== #

def format_timestamp(seconds):
    """Converte segundos em formato de timestamp SRT."""
    td = timedelta(seconds=seconds)
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = td.microseconds // 1000
    return f"{td.days * 24 + hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def get_last_timestamp(srt_file):
    """Obtém o último timestamp de um arquivo SRT (caso tenha sido interrompido)."""
    if not os.path.exists(srt_file):
        return 0
    with open(srt_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        for line in reversed(lines):
            if "-->" in line:
                end_time = line.split(" --> ")[1].strip()
                h, m, s = end_time.split(":")
                s, ms = s.split(",")
                return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    return 0

def get_available_vram():
    """Retorna a quantidade de memória disponível na GPU em bytes."""
    torch.cuda.empty_cache()  # Tentando liberar espaço de memória
    free_mem = torch.cuda.mem_get_info()[0]
    return free_mem

def get_next_log_filename():
    """Gera um nome de log numerado incrementalmente."""
    log_dir = os.path.expanduser("~")
    base_log_name = os.path.join(log_dir, "log")
    index = 1
    while os.path.exists(f"{base_log_name}-{index}.txt"):
        index += 1
    return f"{base_log_name}-{index}.txt"

def log_processing_time(log_file, file_path, start_time, end_time):
    """Registra o tempo de processamento de cada arquivo."""
    duration = end_time - start_time
    with open(log_file, "a", encoding="utf-8") as log:
        log.write(f"Arquivo: {file_path}\n")
        log.write(f"Início: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"Fim: {datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"Duração: {timedelta(seconds=duration)}\n")
        log.write("-" * 50 + "\n")

def display_loading_message():
    """Exibe uma mensagem de carregamento elegante."""
    emojis = ["🧠", "💡", "🚀", "⚡", "💥"]
    for emoji in emojis:
        print(f"{emoji} Carregando, por favor aguarde... {emoji}")
        time.sleep(0.5)  # Simula um efeito de carregamento com atraso

# ============================== PROCESSAMENTO DE ÁUDIO ============================== #

def split_audio(input_file, cache_dir, segment_duration):
    """Converte qualquer arquivo de mídia em segmentos de áudio WAV de 60s."""
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    # Obter duração do arquivo
    result = subprocess.run([
        "ffprobe", "-i", input_file, "-show_entries", "format=duration", "-v", "quiet", "-of", "csv=p=0"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0 or not result.stdout.strip():
        print(f"⚠ Erro ao obter a duração do arquivo: {input_file}")
        return []

    duration = float(result.stdout.strip())
    file_list = []

    for start_time in range(0, int(duration), segment_duration):
        output_file = os.path.join(cache_dir, f"segment_{start_time}.wav")

        if not os.path.exists(output_file):  # Evita recriação desnecessária
            subprocess.run([
                "ffmpeg", "-i", input_file, "-ss", str(start_time), "-t", str(segment_duration),
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", output_file, "-y"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        file_list.append((start_time, output_file))

    return file_list

# ============================== CARREGAMENTO DO MODELO ============================== #

def load_whisper_hybrid():
    """Carrega o modelo Whisper Large de forma híbrida (GPU e RAM)"""
    
    # Verificar se a GPU está disponível
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Exibir status de carregamento
    print(f"🔍 Verificando memória disponível na GPU...")

    # Tentar liberar a memória de vídeo antes de calcular o espaço livre
    torch.cuda.empty_cache()  # Libera a memória não utilizada de forma segura

    # Obter a quantidade de VRAM disponível
    vram_available = get_available_vram()
    print(f"🛠️ Memória disponível na GPU: {vram_available / (1024**2):.2f} MB")

    try:
        # Tente carregar o modelo 'large' (vai rodar na CPU primeiro)
        print("📥 Baixando o modelo 'large'... Pode levar alguns minutos.")
        model = whisper.load_model("large-v3", device="cpu")  
        model = model.to(device, non_blocking=True)  # Mover o modelo para a GPU se disponível
        print("✅ Modelo carregado de forma híbrida!")
    except Exception as e:
        print(f"❌ Erro ao carregar o modelo: {e}")
        raise
    
    return model

# ============================== PROCESSAMENTO DOS ARQUIVOS ============================== #

def transcribe_audio(file_list, srt_file, model, language, resume_from=0):
    """Transcreve arquivos de áudio para um único arquivo SRT."""
    index = 1

    # Verificar se o arquivo SRT já existe e, caso exista, iniciar o índice no próximo número
    if os.path.exists(srt_file):
        with open(srt_file, "r", encoding="utf-8") as srt:
            for line in srt:
                if line.strip().isdigit():
                    index = int(line.strip()) + 1

    # Iterar sobre os segmentos de áudio para transcrição
    for start_time, audio_file in tqdm(file_list, desc=f"🔊 Transcrevendo {srt_file}"):
        if start_time < resume_from:
            continue

        # Realizar a transcrição
        result = model.transcribe(audio_file, language=language)
        print(f"📄 Transcrição completa para {audio_file}.")

        # Adicionar os segmentos transcritos ao arquivo SRT
        with open(srt_file, "a", encoding="utf-8") as srt:
            for segment in result["segments"]:
                segment_start = segment["start"] + start_time
                segment_end = segment["end"] + start_time
                print(f"⌛ Adicionando segmento: {segment_start} --> {segment_end}")
                srt.write(f"{index}\n")
                srt.write(f"{format_timestamp(segment_start)} --> {format_timestamp(segment_end)}\n")
                srt.write(f"{segment['text'].strip()}\n\n")
                index += 1

        os.remove(audio_file)  # Remove o arquivo de áudio depois de processado
        

def process_directory(input_dir, cache_dir, segment_duration, model, language, log_file):
    """Processa todos os arquivos de um diretório de forma sequencial."""
    for file_name in os.listdir(input_dir):
        input_path = os.path.join(input_dir, file_name)
        if os.path.isfile(input_path) and file_name.lower().endswith(('.mp4', '.mkv', '.mp3', '.wav', '.flac', '.m4v', '.avi', '.m4a', '.ogg')):
            # Gerar o nome do arquivo SRT com o mesmo nome do arquivo de entrada
            output_srt = os.path.join(input_dir, f"{os.path.splitext(file_name)[0]}.srt")
            start_time = time.time()

            print(f"📂 Processando: {file_name}")
            
            # Gerar os segmentos de áudio
            audio_segments = split_audio(input_path, cache_dir, segment_duration)

            if not audio_segments:
                print(f"⚠ Erro: Nenhum segmento gerado para {file_name}. Pulando arquivo.")
                continue

            # Transcrever áudio e gerar o arquivo SRT
            transcribe_audio(audio_segments, output_srt, model, language)

            end_time = time.time()
            log_processing_time(log_file, input_path, start_time, end_time)

# ============================== EXECUÇÃO PRINCIPAL ============================== #

def main():
    """Executa o processamento de múltiplos diretórios em fila, um por vez."""
    
    input_dirs = [
        "/media/alan/ssd_1tb1/work/",  # Exemplo de diretório
    ]
    
    cache_dir = "/media/alan/HD_6TB_11/Legendas/cache2"

    segment_duration = 60  # Duração de cada segmento de áudio em segundos
    language = "Portuguese"  # Deixar vazio para detecção automática do idioma

    log_file = get_next_log_filename()
    print(f"📜 Log sendo salvo em: {log_file}")

    display_loading_message()

    model = load_whisper_hybrid()

    for input_dir in input_dirs:
        if os.path.exists(input_dir) and os.listdir(input_dir):
            print(f"🚀 Processando diretório: {input_dir}")
            process_directory(input_dir, cache_dir, segment_duration, model, language, log_file)

    print("✅ Processamento concluído!")

if __name__ == "__main__":
    main()

