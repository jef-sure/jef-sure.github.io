# About

I'm Anton Petrusevich. I have been programming since 1987, when I was in
the seventh grade, and for a living since 1996. Mostly as a hobby, and
sometimes at work, I write
components and programs for ESP32 microcontrollers with displays, in C on
ESP-IDF.

The first of them, in May 2021, was a project to learn the ESP32 and
ESP-IDF: a clock with hands and the weather on a small ST7735 display. DGX
began there, as its graphics library, and became the base of the other
components here: touch input, LVGL on the same displays, a game engine,
boards described as data. Later that year came a clock whose digits were
Bézier curves; the handwritten clock grew out of it. Next to them are drivers for parts my projects used: the SCD4x CO2
sensor, the PN532 and PN5180 NFC readers, the LD2410C presence radar, the
HD44780 character display, and mjson for JSON. All eleven are in the ESP
Component Registry.

Away from microcontrollers there is FIT Visualizer, an extension of VS Code
for the workouts of my bike computer.

| Where | What is there |
| --- | --- |
| [GitHub](https://github.com/jef-sure) | The code. Questions and bug reports go to the issues of each repository. |
| [ESP Component Registry](https://components.espressif.com/components?q=namespace:jef-sure) | The components, ready for `idf.py add-dependency` |
