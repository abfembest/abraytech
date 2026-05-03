
import json
import pycountry
import phonenumbers

output = []
pk = 1

for country in sorted(list(pycountry.countries), key=lambda c: c.name):
    country_name = country.name
    country_code = country.alpha_2

    phone_code = ""
    for code, regions in phonenumbers.COUNTRY_CODE_TO_REGION_CODE.items():
        if country_code in regions:
            phone_code = f"+{code}"
            break

    record = {
        "model": "eduweb.listofcountry",
        "pk": pk,
        "fields": {
            "country": country_name,
            "country_code": country_code,
            "country_phonecode": phone_code
        }
    }

    output.append(record)
    pk += 1

with open("countries.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("countries.json generated successfully with", len(output), "countries.")
