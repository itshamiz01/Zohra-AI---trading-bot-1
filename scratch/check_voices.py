import asyncio
import edge_tts

async def list_voices():
    voices = await edge_tts.list_voices()
    for v in voices:
        locale = v.get("Locale", "")
        gender = v.get("Gender", "")
        if ("hi-IN" in locale or "en-IN" in locale or "ur-PK" in locale or "en-US" in locale) and gender == "Female":
            print(f"{v['ShortName']} | {v['Locale']} | {v['Gender']}")

if __name__ == "__main__":
    asyncio.run(list_voices())
