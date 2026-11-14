with open('scratch/build_gold_command_center.py', 'r', encoding='utf-8') as f:
    code = f.read()

old_func = """        function toggleTalkingDemo(durationSec = 5) {
            holoDemoActive = true;
            isHoloSpeaking = true;

            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
                const utter = new SpeechSynthesisUtterance("Knight, all trading divisions and molecular intelligence circuits are active and synchronized.");
                utter.rate = 1.05;
                utter.pitch = 1.15;
                utter.onend = () => {
                    holoDemoActive = false;
                    isHoloSpeaking = false;
                };
                window.speechSynthesis.speak(utter);
            }

            clearTimeout(holoDemoTimeout);
            holoDemoTimeout = setTimeout(() => {
                holoDemoActive = false;
                isHoloSpeaking = false;
            }, durationSec * 1000);
        }"""

new_func = """        function toggleTalkingDemo(durationSec = 25) {
            if (holoDemoActive) {
                holoDemoActive = false;
                isHoloSpeaking = false;
                clearTimeout(holoDemoTimeout);
                if ('speechSynthesis' in window) window.speechSynthesis.cancel();
                return;
            }
            holoDemoActive = true;
            isHoloSpeaking = true;

            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
                const utter = new SpeechSynthesisUtterance("Knight, all trading divisions and molecular intelligence circuits are active and synchronized.");
                utter.rate = 1.05;
                utter.pitch = 1.15;
                utter.onend = () => {
                    holoDemoActive = false;
                    isHoloSpeaking = false;
                };
                window.speechSynthesis.speak(utter);
            }

            clearTimeout(holoDemoTimeout);
            holoDemoTimeout = setTimeout(() => {
                holoDemoActive = false;
                isHoloSpeaking = false;
            }, durationSec * 1000);
        }"""

if old_func in code:
    code = code.replace(old_func, new_func)
    print("Function updated successfully!")
    with open('scratch/build_gold_command_center.py', 'w', encoding='utf-8') as f:
        f.write(code)
else:
    print("Target function not found!")
