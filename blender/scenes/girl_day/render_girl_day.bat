@echo off
chcp 65001 >nul
rem Рендер ролика «День девочки» на этом ПК (видеокарта), затем склейка в out\girl_day_0001-1500.mp4
rem Если Blender лежит в другом месте — поправь путь ниже.
set BLENDER=C:\blender\Blender 5.2\blender.exe
set GLB=C:\Users\New\Downloads\Meshy_AI_Chibi_Figure_0926172701_texture.glb
cd /d "%~dp0"
"%BLENDER%" -b -P girl_day.py -- --part room   --glb "%GLB%" --out out --render --gpu --samples 32
"%BLENDER%" -b -P girl_day.py -- --part street --glb "%GLB%" --out out --render --gpu --samples 32
"%BLENDER%" -b -P girl_day.py -- --join --out out
echo Готово: папка out
pause
