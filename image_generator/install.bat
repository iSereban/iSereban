@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Установка генератора изображений ===

where python >nul 2>nul
if errorlevel 1 (
    echo Python не найден. Установите Python 3.10-3.12 с python.org
    echo и при установке отметьте галочку "Add Python to PATH".
    pause
    exit /b 1
)

if not exist venv (
    echo Создаю виртуальное окружение...
    python -m venv venv
)
call venv\Scripts\activate.bat

python -m pip install --upgrade pip
echo Устанавливаю PyTorch с поддержкой CUDA (около 2.5 ГБ)...
pip install torch --index-url https://download.pytorch.org/whl/cu124
echo Устанавливаю остальные библиотеки...
pip install -r requirements.txt

python -c "import torch; print('CUDA доступна:', torch.cuda.is_available(), '-', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'нет')"
echo.
echo Готово! Теперь запускайте run.bat
pause
