import os
import torch
import whisper
import subprocess
import shutil
import time
from tqdm import tqdm
from datetime import timedelta, datetime
from concurrent.futures import ThreadPoolExecutor

# ============================== MÉTODOS AUXILIARES ============================== #

def format_timestamp(seconds):
    td = timedelta(seconds=seconds)
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = td.microseconds // 1000
    return f"{td.days * 24 + hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def get_last_timestamp(srt_file):
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
    torch.cuda.empty_cache()
    return torch.cuda.mem_get_info()[0]

def get_next_log_filename():
    log_dir = os.path.expanduser("~")
    base_log_name = os.path.join(log_dir, "log")
    index = 1
    while os.path.exists(f"{base_log_name}-{index}.txt"):
        index += 1
    return f"{base_log_name}-{index}.txt"

def log_processing_time(log_file, file_path, start_time, end_time):
    duration = end_time - start_time
    with open(log_file, "a", encoding="utf-8") as log:
        log.write(f"Arquivo: {file_path}\n")
        log.write(f"Início: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"Fim: {datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"Duração: {timedelta(seconds=duration)}\n")
        log.write("-" * 50 + "\n")

def display_loading_message():
    for emoji in ["🧠", "💡", "🚀", "⚡", "💥"]:
        print(f"{emoji} Carregando, por favor aguarde... {emoji}")
        time.sleep(0.5)

# ============================== PARALELIZAÇÃO FFMPPEG ============================== #

def segment_audio_parallel(input_path, cache_dir, segment_duration):
    filename = os.path.splitext(os.path.basename(input_path))[0]
    temp_dir = os.path.join(cache_dir, f"temp_{filename}")
    os.makedirs(temp_dir, exist_ok=True)

    result = subprocess.run([
        "ffprobe", "-i", input_path, "-show_entries", "format=duration", "-v", "quiet", "-of", "csv=p=0"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0 or not result.stdout.strip():
        print(f"⚠ Erro ao obter a duração do arquivo: {input_path}")
        return []

    duration = float(result.stdout.strip())
    start_times = list(range(0, int(duration), segment_duration))

    def worker(start):
        output_file = os.path.join(temp_dir, f"segment_{start}.wav")
        if not os.path.exists(output_file):
            subprocess.run([
                "ffmpeg", "-i", input_path, "-ss", str(start), "-t", str(segment_duration),
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", output_file, "-y"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return (start, output_file)

    print(f"📊 Gerando {len(start_times)} arquivos de cache em paralelo...")
    with ThreadPoolExecutor() as executor:
        file_list = list(tqdm(executor.map(worker, start_times), total=len(start_times), desc="Criando segmentos de áudio"))

    # Mover os arquivos para a pasta pai
    for _, path in file_list:
        shutil.move(path, os.path.join(cache_dir, os.path.basename(path)))
    shutil.rmtree(temp_dir)
    print(f"✅ Arquivos de cache criados com sucesso!")
    return [(start, os.path.join(cache_dir, f"segment_{start}.wav")) for start, _ in file_list]

# ============================== CARREGAMENTO DO MODELO ============================== #

def load_whisper_hybrid():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"🔍 Verificando memória disponível na GPU...")
    torch.cuda.empty_cache()
    vram_available = get_available_vram()
    print(f"🛠️ Memória disponível na GPU: {vram_available / (1024**2):.2f} MB")
    print("📥 Baixando o modelo 'large'... Pode levar alguns minutos.")
    model = whisper.load_model("large-v3", device="cpu")
    model = model.to(device, non_blocking=True)
    print("✅ Modelo carregado de forma híbrida!")
    return model

# ============================== TRANSCRIÇÃO ============================== #

def transcribe_audio(file_list, srt_file, model, language, resume_from=0):
    index = 1
    if os.path.exists(srt_file):
        with open(srt_file, "r", encoding="utf-8") as srt:
            for line in srt:
                if line.strip().isdigit():
                    index = int(line.strip()) + 1

    for start_time, audio_file in tqdm(file_list, desc=f"🔊 Transcrevendo {srt_file}"):
        if start_time < resume_from:
            continue
        result = model.transcribe(audio_file, language=language)
        with open(srt_file, "a", encoding="utf-8") as srt:
            for segment in result["segments"]:
                segment_start = segment["start"] + start_time
                segment_end = segment["end"] + start_time
                srt.write(f"{index}\n")
                srt.write(f"{format_timestamp(segment_start)} --> {format_timestamp(segment_end)}\n")
                srt.write(f"{segment['text'].strip()}\n\n")
                index += 1
        os.remove(audio_file)

# ============================== PROCESSAMENTO ============================== #

def process_directory(input_dir, cache_dir, segment_duration, model, language, log_file):
    for file_name in os.listdir(input_dir):
        input_path = os.path.join(input_dir, file_name)
        if os.path.isfile(input_path) and file_name.lower().endswith(('.mp4', '.mkv', '.mp3', '.wav', '.flac', '.m4v', '.avi', '.m4a', '.ogg')):
            output_srt = os.path.join(input_dir, f"{os.path.splitext(file_name)[0]}.srt")
            start_time = time.time()
            print(f"📂 Processando: {file_name}")
            audio_segments = segment_audio_parallel(input_path, cache_dir, segment_duration)
            if not audio_segments:
                print(f"⚠ Erro: Nenhum segmento gerado para {file_name}. Pulando.")
                continue
            transcribe_audio(audio_segments, output_srt, model, language)
            end_time = time.time()
            log_processing_time(log_file, input_path, start_time, end_time)

# ============================== MAIN ============================== #

def main():
    input_dirs = ["/home/alan/legendas_whisper/legendar/"]
    cache_dir = "/home/alan/legendas_whisper/caches"
    segment_duration = 60
    language = "Portuguese"
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
