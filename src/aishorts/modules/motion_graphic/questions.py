from aishorts.modules.motion_graphic.motion_graphic import MotionGraphic


class BasicQuestion(MotionGraphic):
    HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@700;800;900&display=swap" rel="stylesheet">
    <style>
        body {
            margin: 0; display: flex; justify-content: center; align-items: center;
            height: 100vh;
            /* Solid chroma-key color (magenta) — removed by ffmpeg chromakey filter on composite */
            background: #FF00FF;
            font-family: 'Poppins', sans-serif;
            perspective: 2500px;
            overflow: hidden;
        }
        * { box-sizing: border-box; }
        .wrapper {
            position: relative;
            width: 750px;
            height: 500px;
            transform-style: preserve-3d;
            opacity: 0;
        }
        .q-mark {
            position: absolute;
            top: -100px;
            left: -100px;
            font-size: 350px;
            color: #FFEA00;
            font-weight: 900;
            z-index: 10;
            line-height: 1;
            opacity: 0;
            transform-origin: bottom center;
            backface-visibility: hidden;
            pointer-events: none;
            white-space: nowrap;
        }
        .card-inner {
            position: relative;
            width: 100%;
            height: 100%;
            transform-style: preserve-3d;
        }
        .card-front, .card-back {
            position: absolute;
            width: 100%;
            height: 100%;
            border-radius: 55px;
            backface-visibility: hidden;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
        .card-front { background: #F2F2F2; z-index: 2; }
        .card-back { background: #33A3FF; color: white; transform: rotateY(180deg); justify-content: center; align-items: center; padding: 80px; text-align: center; }
        .top-bar { background-color:#FF2424; width:100%; height:110px; box-shadow: 0 20px 30px rgba(0,0,0,0.3); flex-shrink: 0; }
        .content {
            position: relative;
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            justify-content: center; 
            align-items: center;
            padding: 60px 60px 120px 60px; 
            text-align: center;
            min-height: 0;
        }
        .title { font-size: 70px; font-weight: 800; color: #242424; line-height: 1.1; width: 100%; word-wrap: break-word; }
        .answer-text { font-size: 110px; font-weight: 900; line-height: 1.1; }
        .progress-container {
            position: absolute;
            bottom: 0px; left: 50%; transform: translateX(-50%);
            width: 120%; height: 50px; background: #E0E0E0; border-radius: 100px; overflow: hidden;
        }
        .progress-fill { height: 100%; background: #33A3FF; width: 100%; border-radius: 100px; }
    </style>
</head>
<body>
    <div class="wrapper" id="master-anim">
        <div class="q-mark" id="q-mark">?</div>
        <div class="card-inner" id="card-inner">
            <div class="card-front">
                <div class="top-bar"></div>
                <div class="content">
                    <div class="title" id="title-text">__QUESTION__</div>
                    <div class="progress-container"><div class="progress-fill" id="progress"></div></div>
                </div>
            </div>
            <div class="card-back"><div class="answer-text" id="answer-text">__ANSWER__</div></div>
        </div>;
    </div>
    <script>
        const titleElement = document.getElementById('title-text');
        const originalText = titleElement.innerText;
        
        function fitText() {
            let fontSize = 69;
            titleElement.style.fontSize = fontSize + 'px';
            const container = titleElement.parentElement;

            const style = window.getComputedStyle(container);
            const maxHeight = container.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
            const maxWidth = container.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);

            titleElement.innerText = originalText;
            while ((titleElement.scrollHeight > maxHeight || titleElement.scrollWidth > maxWidth) && fontSize > 20) {
                fontSize -= 2;
                titleElement.style.fontSize = fontSize + 'px';
            }
            titleElement.innerText = '';
        }
        fitText();

        const answerElement = document.getElementById('answer-text');
        
        function fitAnswer() {
            let fontSize = 110;
            answerElement.style.fontSize = fontSize + 'px';
            const container = answerElement.parentElement;
            const style = window.getComputedStyle(container);
            const maxHeight = container.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
            const maxWidth = container.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);

            while ((answerElement.scrollHeight > maxHeight || answerElement.scrollWidth > maxWidth) && fontSize > 20) {
                fontSize -= 2;
                answerElement.style.fontSize = fontSize + 'px';
            }
        }
        fitAnswer();

        // Standard Back Ease
        function easeOutBack(x) {
            const c1 = 1.70158;
            const c3 = c1 + 1;
            return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
        }

        function updateFrame(time, typingDuration, thinkingDuration, answerDuration) {
            const wrapper = document.getElementById('master-anim');
            const qMark = document.getElementById('q-mark');
            const cardInner = document.getElementById('card-inner');
            
            const flipDuration = 1.0;
            const flipStart = typingDuration + thinkingDuration;
            const exitStart = flipStart + flipDuration + answerDuration; 
            const animTime = 0.8; 

            // ... (Rest of the JS logic is handled by the template, but we pass variables) ...
            // Note: For brevity in this class, I'm assuming the JS logic from the original file 
            // is fully contained here. I've pasted the critical parts above.
            // The full JS logic from the original file should be here.
            
            // 1. MIRRORED WRAPPER LOGIC (Pop-In & Pop-Out)
            // Opacity is held at 1 throughout; scale via easeOutBack (0 → 1 → 0)
            // handles the visual entrance/exit. Fading opacity would blend partial-
            // alpha card pixels into the magenta chroma-key background and show up
            // as pink in the composited video.
            let currentScale = 1;
            let currentRotX = 0;
            let currentRotY = 0;

            if (time < animTime) {
                // --- ENTRANCE ---
                const t = time / animTime;

                currentScale = easeOutBack(t);
                currentRotX = (1 - t) * -20; // Starts at -20, ends at 0
                currentRotY = (1 - t) * 15;  // Starts at 15, ends at 0

            } else if (time > exitStart) {
                // --- EXIT (PERFECT MIRROR) ---
                const t = Math.min(1, (time - exitStart) / animTime);
                const invT = 1 - t;

                // Use the exact same easing function, but backwards (1 -> 0)
                currentScale = easeOutBack(invT);

                // Tilt back to the starting angle (0 -> -20)
                currentRotX = t * -20;
                currentRotY = t * 15;
            }

            wrapper.style.opacity = 1;
            wrapper.style.transform = `scale(${currentScale}) rotateX(${currentRotX}deg) rotateY(${currentRotY}deg)`;

            // 3. CONSTANT IDLE FLOAT
            const floatY = Math.sin(time * 2) * 12;
            const rotXFloat = Math.cos(time * 1.5) * 3;
            const rotYFloat = Math.sin(time * 1.5) * 4.5;

            // 4. FLIP LOGIC
            let flipRotY = 0;
            if (time >= flipStart) {
                const fT = Math.min(1, (time - flipStart) / flipDuration);
                const easedFT = fT < 0.5 ? 4 * fT * fT * fT : 1 - Math.pow(-2 * fT + 2, 3) / 2;
                flipRotY = easedFT * 180;
            }
            // Combine idle float + flip
            cardInner.style.transform = `translateY(${floatY}px) rotateX(${rotXFloat}deg) rotateY(${rotYFloat + flipRotY}deg)`;

            // 5. QUESTION MARK LOGIC
            const qFloatY = Math.cos(time * 2.5) * 9;
            const qFloatRot = Math.sin(time * 2) * 3;

            if (time < flipStart) {
                const qET = Math.min(1, time / 0.6);
                const qSwoop = 1 - Math.pow(1 - qET, 3);
                qMark.style.opacity = Math.min(1, time * 4);
                
                const zPos = -300 + (qSwoop * 450);
                const rotZ = -30 + (qSwoop * 42);
                qMark.style.transform = `translateZ(${zPos}px) translateY(${qFloatY}px) rotateZ(${rotZ + qFloatRot}deg) scale(${qSwoop * 1.1})`;
            } else {
                // Dynamic Exit — bounce away without fading (opacity stays at 1 so
                // partial pixels never blend into the magenta chroma-key background).
                const qExitProgress = Math.min(1, (time - flipStart) / 0.4);
                const exitEase = qExitProgress * qExitProgress; // Accelerate out

                qMark.style.opacity = 1;

                // Move Z forward to avoid clipping with the flipping card (which reaches Z~375)
                const zPos = 150 + (exitEase * 500);
                const yPos = qFloatY - (exitEase * 200);
                const rotZ = 12 + qFloatRot - (exitEase * 45);
                const scale = 1.1 - (exitEase * 0.5);

                qMark.style.transform = `translateZ(${zPos}px) translateY(${yPos}px) rotateZ(${rotZ}deg) scale(${scale})`;
            }

            // 6. TYPING & PROGRESS BAR
            if (time < flipStart) {
                const typeProgress = Math.min(1, time / typingDuration);
                titleElement.innerText = originalText.substring(0, Math.floor(originalText.length * typeProgress));
                const activeTime = Math.max(0, time - typingDuration);
                document.getElementById('progress').style.width = Math.max(0, 100 - (activeTime / thinkingDuration * 100)) + '%';
            } else {
                // After flip starts, hide the question text and freeze the progress bar at 0%
                titleElement.innerText = '';
                document.getElementById('progress').style.width = '0%';
            }
        }
    </script>
</body>
</html>
"""

    def __init__(
        self,
        question: str,
        answer: str,
        typing_duration: float = 3,
        thinking_duration: float = 5,
        answer_duration: float = 2,
    ):
        self.question = question
        self.answer = answer
        self.typing_duration = typing_duration
        self.thinking_duration = thinking_duration
        self.answer_duration = answer_duration

    def get_html(self) -> str:
        return self.HTML_TEMPLATE.replace("__QUESTION__", self.question).replace(
            "__ANSWER__", self.answer
        )

    def get_total_duration(self) -> float:
        # Total time: typing + thinking + flip(1.0) + answer + exit(0.8) + buffer
        return (
            self.typing_duration
            + self.thinking_duration
            + 1.0
            + self.answer_duration
            + 2.0
        )

    def get_javascript_update_call(self, time_passed: float) -> str:
        return f"updateFrame({time_passed}, {self.typing_duration}, {self.thinking_duration}, {self.answer_duration})"
