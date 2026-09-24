"""
Генератор изображений по текстовому описанию (Stable Diffusion, локально).

Настроено под GTX 1660 Super (6 ГБ видеопамяти) + 16 ГБ ОЗУ:
  * float32 — у карт GTX 16xx режим float16 даёт чёрные картинки / NaN;
  * attention slicing + VAE slicing — экономия видеопамяти;
  * при нехватке памяти автоматически включается выгрузка частей модели в ОЗУ.

Запуск из командной строки:
    python generator.py "кот в скафандре на луне, цифровая живопись"
    python generator.py "a castle in the mountains" --model dreamshaper --steps 30 -n 4
"""

import argparse
import re
import time
from datetime import datetime
from pathlib import Path

import torch
from diffusers import (
    AutoPipelineForText2Image,
    DPMSolverMultistepScheduler,
)

# Бесплатные модели с Hugging Face. Скачиваются автоматически при первом запуске
# (2–4 ГБ каждая) и кэшируются в ~/.cache/huggingface.
MODELS = {
    "dreamshaper": {
        "repo": "Lykon/dreamshaper-8",
        "title": "DreamShaper 8 — красивые универсальные картинки (рекомендуется)",
        "steps": 25,
        "guidance": 7.0,
        "size": 512,
    },
    "sd15": {
        "repo": "stable-diffusion-v1-5/stable-diffusion-v1-5",
        "title": "Stable Diffusion 1.5 — оригинальная базовая модель",
        "steps": 25,
        "guidance": 7.5,
        "size": 512,
    },
    "turbo": {
        "repo": "stabilityai/sd-turbo",
        "title": "SD-Turbo — очень быстро (1–4 шага), качество попроще",
        "steps": 4,
        "guidance": 0.0,
        "size": 512,
    },
}
DEFAULT_MODEL = "dreamshaper"

DEFAULT_NEGATIVE = (
    "lowres, blurry, bad anatomy, bad hands, extra fingers, deformed, "
    "ugly, watermark, text, signature, jpeg artifacts"
)

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


def has_cyrillic(text: str) -> bool:
    return bool(re.search(r"[а-яА-ЯёЁ]", text or ""))


def translate_to_english(text: str) -> str:
    """Stable Diffusion понимает в основном английский — переводим русский текст.

    Используется бесплатный Google Translate через deep-translator (нужен интернет).
    Если перевести не удалось, возвращаем текст как есть.
    """
    if not has_cyrillic(text):
        return text
    try:
        from deep_translator import GoogleTranslator

        return GoogleTranslator(source="auto", target="en").translate(text)
    except Exception as exc:  # нет интернета или сервис недоступен
        print(f"[!] Не удалось перевести описание ({exc}). Использую как есть.")
        return text


class ImageGenerator:
    def __init__(self):
        self.pipe = None
        self.model_key = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        # GTX 16xx некорректно работает в float16, поэтому всегда float32.
        self.dtype = torch.float32
        self.offload = False

    def describe_device(self) -> str:
        if self.device == "cuda":
            props = torch.cuda.get_device_properties(0)
            return f"{props.name}, {props.total_memory / 1024**3:.1f} ГБ видеопамяти"
        return "CPU (видеокарта с CUDA не найдена — будет очень медленно!)"

    def load(self, model_key: str = DEFAULT_MODEL):
        if model_key == self.model_key and self.pipe is not None:
            return
        if model_key not in MODELS:
            raise ValueError(f"Неизвестная модель '{model_key}'. Доступны: {', '.join(MODELS)}")

        self.unload()
        cfg = MODELS[model_key]
        print(f"Загружаю модель {cfg['repo']} (первый раз скачивание займёт время)...")

        pipe = AutoPipelineForText2Image.from_pretrained(
            cfg["repo"],
            torch_dtype=self.dtype,
            safety_checker=None,
            requires_safety_checker=False,
            use_safetensors=True,
        )
        if model_key != "turbo":
            # Быстрый и качественный сэмплер: хороший результат за 20–30 шагов.
            pipe.scheduler = DPMSolverMultistepScheduler.from_config(
                pipe.scheduler.config, use_karras_sigmas=True
            )

        pipe.enable_attention_slicing()
        pipe.vae.enable_slicing()
        pipe.vae.enable_tiling()  # позволяет делать картинки крупнее 512px
        pipe.set_progress_bar_config(disable=False)

        if self.device == "cuda":
            pipe.to("cuda")
        self.pipe = pipe
        self.model_key = model_key
        self.offload = False
        print("Модель загружена.")

    def unload(self):
        self.pipe = None
        self.model_key = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def _enable_offload(self):
        """Запасной режим при нехватке видеопамяти: части модели лежат в ОЗУ."""
        if self.offload or self.device != "cuda":
            return False
        print("[!] Не хватило видеопамяти — включаю выгрузку модели в ОЗУ (медленнее).")
        self.pipe.to("cpu")
        torch.cuda.empty_cache()
        self.pipe.enable_model_cpu_offload()
        self.offload = True
        return True

    def generate(
        self,
        prompt: str,
        negative_prompt: str = DEFAULT_NEGATIVE,
        model_key: str = DEFAULT_MODEL,
        steps: int | None = None,
        guidance: float | None = None,
        width: int = 512,
        height: int = 512,
        seed: int = -1,
        num_images: int = 1,
        translate: bool = True,
        save: bool = True,
    ):
        """Возвращает (список картинок PIL, использованный seed, итоговый промпт)."""
        if not prompt or not prompt.strip():
            raise ValueError("Пустое описание.")

        self.load(model_key)
        cfg = MODELS[model_key]
        steps = steps or cfg["steps"]
        guidance = cfg["guidance"] if guidance is None else guidance
        # Размеры должны делиться на 8.
        width, height = int(width) // 8 * 8, int(height) // 8 * 8

        if translate:
            prompt = translate_to_english(prompt)
            negative_prompt = translate_to_english(negative_prompt)
            print(f"Промпт: {prompt}")

        if seed is None or int(seed) < 0:
            seed = int(torch.randint(0, 2**31 - 1, (1,)).item())
        seed = int(seed)

        images = []
        start = time.time()
        for i in range(int(num_images)):
            generator = torch.Generator("cpu").manual_seed(seed + i)
            kwargs = dict(
                prompt=prompt,
                negative_prompt=negative_prompt if guidance > 1 else None,
                num_inference_steps=int(steps),
                guidance_scale=float(guidance),
                width=width,
                height=height,
                generator=generator,
            )
            try:
                image = self.pipe(**kwargs).images[0]
            except torch.cuda.OutOfMemoryError:
                if not self._enable_offload():
                    raise
                image = self.pipe(**kwargs).images[0]
            images.append(image)
            if save:
                path = self.save(image, prompt, seed + i)
                print(f"Сохранено: {path}")

        print(f"Готово за {time.time() - start:.1f} c.")
        return images, seed, prompt

    @staticmethod
    def save(image, prompt: str, seed: int) -> Path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", prompt).strip("_")[:50] or "image"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = OUTPUT_DIR / f"{stamp}_{seed}_{slug}.png"
        image.save(path)
        return path


def main():
    parser = argparse.ArgumentParser(description="Генерация изображения по текстовому описанию")
    parser.add_argument("prompt", help="описание картинки (можно по-русски)")
    parser.add_argument("--negative", default=DEFAULT_NEGATIVE, help="чего НЕ должно быть на картинке")
    parser.add_argument("--model", choices=list(MODELS), default=DEFAULT_MODEL)
    parser.add_argument("--steps", type=int, default=None, help="количество шагов (больше — дольше и детальнее)")
    parser.add_argument("--guidance", type=float, default=None, help="насколько строго следовать описанию (обычно 5–9)")
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--seed", type=int, default=-1, help="-1 = случайный")
    parser.add_argument("-n", "--num", type=int, default=1, help="сколько картинок сделать")
    parser.add_argument("--no-translate", action="store_true", help="не переводить описание на английский")
    args = parser.parse_args()

    gen = ImageGenerator()
    print(f"Устройство: {gen.describe_device()}")
    _, seed, _ = gen.generate(
        prompt=args.prompt,
        negative_prompt=args.negative,
        model_key=args.model,
        steps=args.steps,
        guidance=args.guidance,
        width=args.width,
        height=args.height,
        seed=args.seed,
        num_images=args.num,
        translate=not args.no_translate,
    )
    print(f"Seed: {seed}  (укажите --seed {seed}, чтобы повторить результат)")


if __name__ == "__main__":
    main()
