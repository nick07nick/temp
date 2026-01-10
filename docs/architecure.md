# Архитектурная спецификация: BikeFit Core v2.1 (Security Enhanced)

**Изменения относительно v2.0:** Интегрирован слой защиты (Security Layer), изменены протоколы памяти (Obfuscated Storage) и добавлен контроллер лицензий.

## 1. Концепция: Secure Distributed Node

Система работает как набор изолированных процессов, связанных через Shared Memory. Однако, **данные в памяти зашифрованы математически** («отравлены»). Без наличия USB-ключа, который генерирует валидные коэффициенты (Salt) в реальном времени, система работает, но выдает биомеханически неверные данные.

---

## 2. Основные компоненты системы

### 2.1. ProcessorOrchestrator (Главный процесс)

В дополнение к функциям менеджера процессов, теперь включает:

- **SecurityController (Thread):**
  
  - Монопольно держит связь с USB-ключом (`ICryptoProvider`).
    
  - **Heartbeat & Watchdog:** Каждые 500мс опрашивает ключ (Challenge-Response). Если задержка > 15мс — блокирует работу (защита от сетевого шеринга).
    
  - **Salt Generator:** Генерирует и обновляет `MathSalt` (коэффициент искажения) и кладет его в защищенную область памяти (`SecureParams`).
    

### 2.2. CameraWorker (Узел камеры)

- **Secure Pipeline:**
  
  - Получает кадр.
    
  - Читает текущий `MathSalt` из памяти (или использует кэшированный).
    
  - **Poisoned Detection:** Детектирует точки, но перед записью в буфер применяет формулу: `stored_val = real_val * MathSalt`.
    
  - **Flash Detection:** Если средняя яркость кадра резко выросла, выставляет флаг `SYNC_EVENT` в заголовке кадра.
    

### 2.3. Shared Memory (Obfuscated Protocol)

Мы отказываемся от хранения чистых `float` координат в открытом виде.

- Используется бинарная упаковка (`struct`).
  
- Формат хранения координат: `int32` (Fixed Point c динамической солью).
  

---

## 3. Потоки данных (Data Flow)

### 3.1. Secure Memory Protocol

Вместо `[frame_id, timestamp, pixels]` структура пакета расширяется:

Python

```
# Структура заголовка (Header)
struct FrameHeader {
    uint64_t frame_id;    # Номер кадра
    double   timestamp;   # Время захвата
    float    math_salt;   # Соль, с которой был записан этот кадр (для расшифровки Ядром)
    uint8_t  flags;       # Битовая маска: 0x01=SYNC_FLASH, 0x02=LOW_LIGHT
    uint16_t count;       # Кол-во точек
}
```

### 3.2. Жизненный цикл защиты (The Loop)

1. **Orchestrator:** Запрашивает USB-ключ -> получает `GlobalSalt` -> пишет в `ControlQueue` всех воркеров.
  
2. **CameraWorker:** Применяет `GlobalSalt` к координатам -> пишет в SHM.
  
3. **Core / API:** Читает SHM -> Читает `math_salt` из заголовка -> Делит: `real_val = stored_val / math_salt`.
  
4. **Атака (Memory Dump):** Если хакер дампит память, он видит координаты `349204, -123002`. Без знания `math_salt` (который меняется), эти цифры бесполезны.
  

---

## 4. Обновленная структура классов

### 4.1. Interfaces (src/core/interfaces.py)

Python

```
class ICryptoProvider(ABC):
    @abstractmethod
    def get_math_salt(self) -> float: ...
    @abstractmethod
    def check_license(self) -> bool: ...
```

### 4.2. Models (src/data/models.py)

Добавляем поддержку бинарных флагов для Flash Align.

Python

```
class FrameFlags:
    NONE = 0
    FLASH_DETECTED = 1 << 0  # 0x01
    MOVEMENT_DETECTED = 1 << 1 # 0x02
```

---

## 5. План рефакторинга (С учетом безопасности)

### Этап 1: Secure Foundation (Критично)

1. **SharedMemory:** Реализовать поддержку структур `struct` с полями `math_salt` и `flags`.
  
2. **CryptoProvider:** Реализовать `DevCryptoProvider` (заглушка) и архитектуру для подключения реального `UsbCryptoProvider`.
  
3. **EventBus:** Без изменений, но добавить каналы для `SecurityAlerts`.
  

### Этап 2: Orchestration & Security

1. Написать `ProcessorOrchestrator` с интегрированным `SecurityController`.
  
2. Реализовать логику обновления соли (пока эмуляцию).
  

### Этап 3: Camera Worker

1. Внедрить алгоритм детекции вспышки (простой подсчет средней яркости).
  
2. Внедрить применение соли к координатам перед записью.



# ОПИСАНИЕ АРХИТЕКТУРЫ ПОСЛЕ РЕФАКТОРИНГА

Вот полная картина архитектуры **BikeFit Core v3.0 (Secure Distributed Edition)**, к которой мы пришли после рефакторинга.

Эта структура обеспечивает работу **6–10 камер на 90 FPS**, защиту от сбоев (изоляция процессов) и защиту от пиратства («отравленная математика»).

---

## 1. Концепция: Распределенный Узел (Distributed Node)

Система больше не является монолитным циклом. Это набор независимых процессов, которые общаются через **Общую Память (Shared Memory)** для видео и **Шину Событий (Event Bus)** для управления.

### Ключевые изменения относительно v1.0:

1. **Изоляция:** Каждая камера живет в своем процессе OS. Падение камеры не роняет сервер.
  
2. **Безопасность:** Координаты в памяти хранятся в «отравленном» виде (умноженные на соль).
  
3. **Гибридный пайплайн:** Быстрая обработка (Undistort/Threshold) внутри воркера, тяжелая (NN) — в будущем в отдельных процессах.
  

---

## 2. Основные Компоненты

### А. `ProcessorOrchestrator` (Мозг системы)

- **Где живет:** Главный процесс (`src/core/orchestrator.py`).
  
- **Что делает:**
  
  1. **Process Manager:** Запускает процессы `CameraWorker` для каждой камеры.
    
  2. **Supervisor:** Следит за здоровьем процессов (Health Check). Если воркер упал или завис (нет Heartbeat) — перезапускает его.
    
  3. **Security Controller:** Держит связь с USB-ключом (эмуляция), генерирует `MathSalt` и рассылает его воркерам.
    
  4. **Aggregator:** Собирает метаданные (FPS, статусы) в единый `SystemState`.
    

### Б. `CameraWorker` (Рабочая лошадка)

- **Где живет:** Отдельный процесс (`src/hardware/camera_worker.py`).
  
- **Что делает:**
  
  1. **Hardware Owner:** Монопольно владеет объектом `Webcam` (драйвер).
    
  2. **Memory Owner:** Создает и управляет `SharedMemory` (Ring Buffer).
    
  3. **Security Enforcer:**
    
    - Принимает `MathSalt` от Оркестратора.
      
    - Детектирует вспышки (`SYNC_FLASH`) для синхронизации.
      
    - Пишет в память данные, защищенные солью и флагами.
      
  4. **Sync Pipeline:** Запускает легкие стадии обработки (`Processor` внутри процесса) перед записью в память.
    

### В. `SharedMemoryManager` (Транспорт видео)

- **Где живет:** Разделяемая память OS (`/dev/shm` на Linux).
  
- **Протокол:** Бинарный `struct` (Secure Protocol v2.1).
  
- **Структура кадра:**
  
  C++
  
  ```
  struct Frame {
      int64_t frame_id;
      double  timestamp;
      float   math_salt;   // <-- Множитель защиты
      uint8_t flags;       // <-- Битовая маска (Flash, Motion)
      byte[]  pixels;      // <-- Картинка
  }
  ```
  

### Г. `EventBus` (Нервная система)

- **Где живет:** `multiprocessing.Queue` (`src/core/event_bus.py`).
  
- **Что делает:**
  
  - **Command Queue:** Оркестратор -> Воркер (например, `SET_EXPOSURE`, `SET_SALT`).
    
  - **Upstream Queue:** Воркер -> Оркестратор (например, `HEARTBEAT`, `STREAM_DATA`, `ERROR`).
    

### Д. `APIServer` (Интерфейс)

- **Где живет:** Отдельный процесс (`src/api/server.py`).
  
- **Что делает:**
  
  1. **Streamer:** Читает кадры из Shared Memory (только чтение) и отдает MJPEG на фронт.
    
  2. **WebSocket:** Транслирует `SystemState` (координаты, статусы) в реальном времени.
    
  3. **API Gateway:** Принимает REST запросы и конвертирует их в команды для EventBus.
    

---

## 3. Схема Взаимодействия

### Поток 1: Видео и Данные (Fast Path)

1. **Webcam:** Захват кадра (RAW).
  
2. **CameraWorker:**
  
  - Детекция вспышки -> установка флага `SYNC_FLASH`.
    
  - Применение `MathSalt` к координатам.
    
  - Запись в `SharedMemory` (Slot N).
    
3. **APIServer:** Чтение Slot N -> Кодирование в JPEG -> Отправка в браузер.
  

### Поток 2: Управление и Безопасность (Control Path)

1. **Orchestrator (SecurityController):** Генерирует новую соль (раз в 5 сек).
  
2. **EventBus:** Передает команду `SET_SALT` конкретному воркеру.
  
3. **CameraWorker:** Обновляет локальный множитель. Следующий кадр будет записан с новой солью.
  

### Поток 3: Обработка сбоев (Self-Healing)

1. **CameraWorker:** Раз в 1 сек шлет `HEARTBEAT` в шину.
  
2. **Orchestrator:** Проверяет: «Приходил ли сигнал от Cam-0 за последние 3 сек?».
  
3. **Сбой:** Если нет — убивает процесс (SIGKILL) и запускает новый.
  

---

## 4. Итоговая структура файлов (Refactored)

Те файлы, которые мы изменили и утвердили:

- `src/main.py` — Точка входа. Запускает Оркестратор и API.
  
- `src/core/orchestrator.py` — Управление процессами и Безопасностью.
  
- `src/hardware/camera_worker.py` — Логика процесса камеры.
  
- `src/hardware/webcam.py` — Чистый драйвер (только захват).
  
- `src/core/processor.py` — Конвейер обработки (Pipeline) с защитой от ошибок плагинов.
  
- `src/data/shared_memory.py` — Новый бинарный протокол с защитой.
  
- `src/api/server.py` — Сервер, умеющий читать новый протокол.








# Руководство по архитектуре и созданию виджетов


Вот полная, объединенная и дополненная документация. Она включает в себя архитектурный обзор (на основе `architecture.md`) и подробное руководство по созданию пары «Плагин (Бэкенд) + Виджет (Фронтенд)», учитывая все особенности вашей реализации (Registry, Wrappers, Context).

---

# 📘 BikeFit Core v3.0: Архитектура и Руководство Разработчика

Данный документ описывает устройство системы BikeFit Core v3.0 (Secure Distributed Edition) и предоставляет пошаговую инструкцию по созданию новых модулей (плагинов и виджетов).

---

## Часть 1. Архитектура Системы

Система построена как набор изолированных процессов, обменивающихся данными через **Shared Memory** (видеопоток) и **EventBus** (управление).

### 1.1. Основные Компоненты

1. **ProcessorOrchestrator (Main Process):**
* Управляет жизненным циклом воркеров камер.
* **Security Controller:** Генерирует "соль" (`MathSalt`) для защиты данных памяти. Без этой соли координаты в памяти являются математическим мусором.
* Маршрутизирует команды между фронтендом и воркерами.


2. **CameraWorker (Process per Camera):**
* Захватывает кадры.
* Запускает **Processor** (пайплайн обработки).
* Сохраняет "отравленные" (защищенные) данные в Shared Memory.


3. **Processor (Pipeline Engine):**
* Загружает и выполняет **Плагины (Stages)**.
* Собирает данные от всех плагинов в единый `FrameContext`.
* Формирует JSON-снапшот состояния (`SystemState`) для отправки на фронтенд.


4. **APIServer & WebSocket:**
* Транслирует видео (MJPEG).
* Обеспечивает двустороннюю связь через WebSocket:
* **Downstream:** Бэкенд -> Фронтенд (Данные виджетов, уведомления).
* **Upstream:** Фронтенд -> Бэкенд (Команды кнопок).





### 1.2. Поток Данных (Data Flow)

1. **Бэкенд:** Плагин вызывает `ctx.ui.update_widget(...)`.
2. **Processor:** Собирает эти обновления в список `widgets`.
3. **EventBus:** Передает пакет Оркестратору, затем API серверу.
4. **WebSocket:** Отправляет JSON в браузер.
5. **Frontend (RobotContext):** Распаковывает JSON и обновляет стейт `widgetsData`.
6. **Registry (Wrapper):** Достает данные по ID и передает их в React-компонент.

---

## Часть 2. Руководство: Создание Плагина (Backend)

Плагин — это Python-класс, который обрабатывает видео или логику.

**Где создавать:** `src/plugins/` (система сама найдет файл).

### Шаблон Плагина

```python
from src.core.pipeline import PipelineStage, FrameContext
from loguru import logger
import time

class MyFeaturePlugin(PipelineStage):
    def __init__(self):
        # Имя плагина. Оно же используется как target для команд.
        super().__init__("my_feature") 
        self.counter = 0

    def process(self, ctx: FrameContext):
        """Вызывается для каждого кадра"""
        
        # 1. Чтение данных
        # ctx.frame - текущий кадр (numpy array)
        # ctx.config - конфиг камеры
        
        # 2. Логика (пример)
        self.counter += 1
        
        # 3. Отправка данных на Фронтенд (в Виджет)
        # widget_id: ID, по которому виджет найдет данные в Registry
        payload = {
            "val": self.counter,
            "status": "active"
        }
        ctx.ui.update_widget(widget_id="my_feature_widget", title="My Feature", data=payload)

    def handle_command(self, cmd: str, args: dict):
        """Обработка команд от кнопок виджета"""
        logger.info(f"📨 MyFeature received: {cmd}")
        
        if cmd == "reset":
            self.counter = 0

```

### Правила Бэкенда:

1. **Наследование:** Всегда наследуйтесь от `PipelineStage`.
2. **UI Updates:** Используйте `ctx.ui.update_widget`, чтобы отправить данные конкретному виджету.
3. **Commands:** Реализуйте метод `handle_command` для реакции на кнопки.

---

## Часть 3. Руководство: Создание Виджета (Frontend)

Виджет — это React-компонент, который отображает данные и отправляет команды.

**Где создавать:** `src/components/` (или `src/widgets/`).

### Шаблон Виджета

```jsx
import React from 'react';

// Виджет получает два пропса:
// data - объект данных, пришедший с бэкенда
// sendCommand - функция для отправки команд
export const MyFeatureWidget = ({ data, sendCommand }) => {
    
    // 1. Распаковка данных (Safety Check)
    // RobotContext оборачивает данные, поэтому берем .data или сам объект
    const payload = data?.data || data || {};
    
    const value = payload.val || 0;
    const status = payload.status || 'Loading...';

    // 2. Отправка команды
    const handleReset = () => {
        console.log("Sending reset...");
        // target: должен совпадать с именем плагина в Python (super().__init__("my_feature"))
        // cmd: имя команды
        // args: любые параметры
        if (sendCommand) {
            sendCommand('my_feature', 'reset', {}); 
        }
    };

    return (
        <div style={{ padding: 20, color: 'white', background: '#1e293b' }}>
            <h3>My Feature</h3>
            <div>Value: {value}</div>
            <div>Status: {status}</div>
            
            <button onClick={handleReset}>Reset Counter</button>
        </div>
    );
};

```

### Правила Фронтенда:

1. **Распаковка:** Всегда используйте конструкцию `const payload = data?.data || {};`, так как данные могут приходить в обертке.
2. **Проверка sendCommand:** Убедитесь, что функция существует перед вызовом.
3. **Target:** Первый аргумент `sendCommand` — это имя плагина на бэкенде.

---

## Часть 4. Регистрация (Связывание Бэка и Фронта)

Чтобы виджет появился в интерфейсе и получил доступ к данным, его нужно зарегистрировать в `registry.js` через **Wrapper (Обертку)**.

**Файл:** `src/widgets/registry.js`

### Почему нужен Wrapper?

React-библиотека `react-grid-layout`, которую мы используем, не умеет сама прокидывать пропсы (`data`, `sendCommand`) в виджеты. Мы должны сделать это вручную, подключившись к `RobotContext`.

### Шаг 1. Создание Wrapper-а

Добавьте этот код в `registry.js` перед экспортом `WIDGET_REGISTRY`:

```javascript
import { MyFeatureWidget } from '../components/MyFeatureWidget'; // Импорт вашего компонента
import { useRobot } from '../context/RobotContext';

// ... другие импорты ...

// Создаем связующий компонент
const MyFeatureWrapper = () => {
    const { sendCommand, widgetsData } = useRobot();
    
    // "my_feature_widget" - это ID, который вы указали в Python:
    // ctx.ui.update_widget("my_feature_widget", ...)
    const data = widgetsData['my_feature_widget'] || {};
    
    return <MyFeatureWidget data={data} sendCommand={sendCommand} />;
};

```

### Шаг 2. Добавление в Registry

Добавьте запись в объект `WIDGET_REGISTRY`:

```javascript
export const WIDGET_REGISTRY = {
    // ... другие виджеты ...
    
    'my_feature_ui': {           // Уникальный ключ для системы лейаутов
        title: 'Super Feature',  // Заголовок окна
        component: MyFeatureWrapper, // Используем Wrapper, а не сам Widget!
        defaultW: 4,             // Ширина (в колонках сетки)
        defaultH: 6              // Высота
    }
};

```

---

## Чек-лист для проверки "Почему не работает?"

1. **Данные не приходят:**
* Проверьте `widget_id` в Python (`ctx.ui.update_widget`) и в `registry.js` (`widgetsData['...']`). Они должны совпадать **буква в букву**.
* Проверьте, что плагин загружен (в логах бэкенда: `🔌 Discovered Plugin`).


2. **Команды не работают:**
* Ошибка `sendCommand is not a function`? -> Вы забыли использовать **Wrapper** в `registry.js` или не передали `sendCommand` в пропсы.
* Команда уходит, но ничего не происходит? -> Проверьте `target` в `sendCommand('TARGET', ...)` и имя в `super().__init__("TARGET")`.


3. **Картинка не показывается:**
* Убедитесь, что в Python вы формируете строку `data:image/jpeg;base64,...`.
* В React используйте `<img src={payload.image_src} />`.



## ⚡ Разработка плагинов: Best Practices (v2.1)

### 1. Управление ресурсами (Throttling)

Система работает на 90 FPS. Тяжелые CV-алгоритмы (поиск маркеров, нейросети) **не должны** запускаться на каждом кадре, если это не критично для трекинга. Используйте троттлинг:

Python

```
self.FPS_PROCESS = 15.0 # Достаточно для UI/Настройки
if (time.time() - self.last_time) < (1.0 / self.FPS_PROCESS):
    return
```

### 2. Структура команд (EventBus)

Для общения с Hardware-воркерами используйте метод `send_command` с тремя аргументами. **Запрещено**формировать payload вручную.

Python

```
# ✅ Правильно:
ctx.bus.send_command(f"cam_{ctx.camera_id}", "SET_CONFIG", {"gain": 10})

# ❌ Неправильно:
ctx.bus.send_command(0, {"cmd": "SET_CONFIG", "args": ...})
```

### 3. Файловая система

Все конфигурационные файлы плагинов должны храниться в папке `/config` в корне проекта. Для доступа к путям используйте глобальную переменную:

Python

```
from src.core.config import ROOT_DIR
config_path = ROOT_DIR / "config" / "plugin_name.json"
```

### 4. Жизненный цикл (Lifecycle)

Если ваш плагин имеет UI (виджет), он должен реагировать на скрытие окна, чтобы не потреблять ресурсы. Реализуйте в `handle_command`:

- `wizard_opened` -> Включить обработку и стриминг.
  
- `wizard_closed` -> Выключить все (`return` в начале `process`).
  
- `toggle_pause` -> Остановить расчеты, но оставить стриминг (для отладки)