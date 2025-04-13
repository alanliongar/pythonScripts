import os
import torch
import whisper
import subprocess
import time
import shutil
from tqdm import tqdm
from datetime import timedelta, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================== CONFIGURAÇÃO ============================== #

# Define os diretórios e os idiomas desejados
PROCESSING_MAP = {
    "C:/midia/dir1": ["English", "Portuguese", "Italian"],
    "C:/midia/dir2": ["English"],
    "C:/midia/dir3": [None],
}

CACHE_DIR = "G:/Legendas/cache1"
SEGMENT_DURATION = 60

# ============================== FUNÇÕES AUXILIARES ============================== #

def format_timestamp(seconds):
    td = timedelta(seconds=seconds)
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = td.microseconds // 1000
    return f"{td.days * 24 + hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

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
    emojis = ["🦰", "💡", "🚀", "⚡", "💥"]
    for emoji in emojis:
        print(f"{emoji} Carregando, por favor aguarde... {emoji}")
        time.sleep(0.5)

# ============================== SEGMENTAÇÃO OTIMIZADA ============================== #

def extract_segment(input_path, start_time, segment_duration, output_file):
    subprocess.run([
        "ffmpeg", "-i", input_path, "-ss", str(start_time), "-t", str(segment_duration),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", output_file, "-y"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def split_audio_parallel(input_path, cache_path, segment_duration):
    result = subprocess.run([
        "ffprobe", "-i", input_path, "-show_entries", "format=duration", "-v", "quiet", "-of", "csv=p=0"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0 or not result.stdout.strip():
        print(f"⚠ Erro ao obter a duração do arquivo: {input_path}")
        return []

    duration = float(result.stdout.strip())
    segment_starts = list(range(0, int(duration), segment_duration))
    temp_dir = os.path.join(cache_path, f"temp_{os.path.splitext(os.path.basename(input_path))[0]}")
    os.makedirs(temp_dir, exist_ok=True)

    print(f"📊 Criando {len(segment_starts)} segmentos para {input_path}...")
    with ThreadPoolExecutor() as executor:
        futures = []
        for start in segment_starts:
            output_file = os.path.join(temp_dir, f"segment_{start}.wav")
            futures.append(executor.submit(extract_segment, input_path, start, segment_duration, output_file))

        for _ in tqdm(as_completed(futures), total=len(futures), desc="Criando .wav"):
            pass

    for file in os.listdir(temp_dir):
        shutil.move(os.path.join(temp_dir, file), os.path.join(cache_path, file))
    shutil.rmtree(temp_dir)

    print("✅ Segmentos prontos!")
    return [(start, os.path.join(cache_path, f"segment_{start}.wav")) for start in segment_starts]

# ============================== WHISPER ============================== #

def load_whisper_hybrid():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.cuda.empty_cache()
    print(f"🔍 Memória de GPU: {torch.cuda.mem_get_info()[0] / (1024**2):.2f} MB livres")
    model = whisper.load_model("large-v3", device="cpu").to(device, non_blocking=True)
    return model

def transcribe_audio(file_list, srt_file, model, language):
    index = 1
    with open(srt_file, "a", encoding="utf-8") as srt:
        for start_time, audio_file in tqdm(file_list, desc=f"🔊 Transcrevendo {srt_file}"):
            result = model.transcribe(audio_file, language=language)
            for segment in result["segments"]:
                segment_start = segment["start"] + start_time
                segment_end = segment["end"] + start_time
                srt.write(f"{index}\n")
                srt.write(f"{format_timestamp(segment_start)} --> {format_timestamp(segment_end)}\n")
                srt.write(f"{segment['text'].strip()}\n\n")
                index += 1
            os.remove(audio_file)

# ============================== LOOP PRINCIPAL ============================== #

def process_directory(input_dir, cache_dir, segment_duration, model, languages, log_file):
    for file in os.listdir(input_dir):
        if not file.lower().endswith((".mp4", ".mkv", ".mp3", ".wav", ".flac", ".m4v", ".avi", ".m4a", ".ogg")):
            continue

        input_path = os.path.join(input_dir, file)
        base = os.path.splitext(file)[0]

        print(f"\n📂 Processando: {file}")
        start_time = time.time()

        segments = split_audio_parallel(input_path, cache_dir, segment_duration)

        for lang in languages:
            lang_suffix = f".{lang}" if lang else ""
            srt_path = os.path.join(input_dir, f"{base}{lang_suffix}.srt")
            transcribe_audio(segments.copy(), srt_path, model, lang)

        end_time = time.time()
        log_processing_time(log_file, input_path, start_time, end_time)

# ============================== MAIN ============================== #

def main():
    log_file = get_next_log_filename()
    display_loading_message()
    model = load_whisper_hybrid()

    for input_dir, languages in PROCESSING_MAP.items():
        if os.path.exists(input_dir):
            print(f"\n🚀 Processando diretório: {input_dir}")
            process_directory(input_dir, CACHE_DIR, SEGMENT_DURATION, model, languages, log_file)

    print("\n✅ Tudo finalizado!")

if __name__ == "__main__":
    main()

