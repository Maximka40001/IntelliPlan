from groq import Groq
import json

client = Groq(api_key="")  # Вставьте свой ключ

def extract_absence_info(text):
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": """Ты помощник, который извлекает информацию об отсутствии преподавателей.
Верни ТОЛЬКО валидный JSON в формате:
{
    "teacher_surname": "фамилия преподавателя",
    "absence_dates": ["дата1", "дата2", ...]
}

Если даты указаны как диапазон (например "с 1 по 5"), преобразуй в список дат.
Если месяц не указан, используй текущий месяц."""
            },
            {
                "role": "user",
                "content": text
            }
        ],
        temperature=0.3,  # Низкая температура для более предсказуемых результатов
        max_completion_tokens=1024,
        top_p=1,
        stream=False,  # Отключаем stream для удобства парсинга JSON
        response_format={"type": "json_object"}  # Принудительный JSON формат
    )
    
    response_text = completion.choices[0].message.content
    return json.loads(response_text)

# Пример использования
text = ""
result = extract_absence_info(text)
print(json.dumps(result, ensure_ascii=False, indent=2))