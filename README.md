# ☀️ Сумдын нарны эрчим хүчний хангамжийн төлөвлөлт

Монголын сумдыг **батарейтай нарны системээр** хамгийн бага зардлаар хэрхэн хангах
вэ гэдгийг шугамын **нэвтрүүлэх чадварыг** харгалзан тооцоолж, интерактив газрын
зураг дээр харуулдаг веб апп.

## Юу хийдэг вэ

- **soums.xlsx** — сумдын байршил, хэрэглээ (кВт)
- **lines.xlsx** — шугамын байршил, урт, хүчдэл, нэвтрүүлэх чадвар (МВт)
- Шугамаар холбогдсон сүлжээ (network) бүрт:
  - **Тараангуй** (сум бүр өөрийн станц) ба **Төвлөрсөн** (нэг станц бүгдийг хангах)
    хувилбарыг тооцоолж, шугамын чадвар хүрэлцэх эсэхийг шалган **хямдыг** нь зөвлөнө.
- Сум/зангилаа дээр дарахад нарны систем, батарей, өртөг, нийлбэр ачаалал харагдана.

## Тооцооллын загвар

Хэрэглээг оргил чадал (кВт) бөгөөд өдөрт 24 цаг ажиллана гэж үзнэ:

| Үе шат | Томьёо |
|--------|--------|
| Өдрийн эрчим | `E = Хэрэглээ_кВт × 24` |
| Нарны чадал | `PV = E / (PSH × PR)` |
| Батарей | `Battery = E × нөөц / (DoD × ашиг)` |
| Өртөг | `тогтмол + (PV$ + Батарей$) × угсралт` |

Анхны таамаглал: PSH 4.5 ц, PR 0.75, нөөц 1 өдөр, DoD 0.8, панель 550 Вт,
PV $0.9/Вт, батарей $350/кВт·ц, станцын тогтмол зардал $8000. **Бүгдийг апп дотор
гулсуураар тохируулж болно.**

> Шугамын чадвар тодорхойгүй (хоосон) бол "хүрэлцэнэ" гэж үзэж, аппад тэмдэглэнэ.

## Локал ажиллуулах

```bash
pip install -r requirements.txt
streamlit run app.py
```

Статик HTML газрын зураг (Streamlit-гүй):

```bash
python generate_map.py        # mongolia_electricity_map.html үүснэ
```

## Docker контейнер

```bash
# 1. Image байгуулах
docker build -t soums-solar .

# 2. Контейнер ажиллуулах (8501 порт)
docker run -p 8501:8501 soums-solar
```

Дараа нь браузерт **http://localhost:8501** нээнэ. PuLP-ийн CBC солвер нь Linux
wheel дотроо ирдэг тул нэмэлт системийн хамаарал шаардахгүй.

## Интернетэд байршуулах — Streamlit Community Cloud (үнэгүй)

> Энэ хэсгийг та өөрөө GitHub болон Streamlit дансаараа хийнэ.

**1. GitHub repo үүсгэх ба код байршуулах**

```bash
cd c:\Apps\soums
git init
git add app.py solar.py network.py mapbuilder.py generate_map.py `
        requirements.txt README.md soums.xlsx lines.xlsx
git commit -m "Нарны хангамжийн төлөвлөлтийн апп"
```

Дараа нь [github.com](https://github.com)-д шинэ repo (жишээ `soums-solar`) үүсгээд:

```bash
git remote add origin https://github.com/<таны-нэр>/soums-solar.git
git branch -M main
git push -u origin main
```

**2. Streamlit Cloud-д холбох**

1. [share.streamlit.io](https://share.streamlit.io) → **Sign in with GitHub**
2. **Create app** → **Deploy a public app from GitHub**
3. Сонгох:
   - Repository: `<таны-нэр>/soums-solar`
   - Branch: `main`
   - Main file path: `app.py`
4. **Deploy** дарна. 1-2 минутын дотор апп `https://<нэр>.streamlit.app` хаягтай
   нийтэд нээлттэй болно.

**3. Шинэчлэх:** код өөрчилж `git push` хийхэд апп автоматаар дахин deploy хийгдэнэ.

## Файлын бүтэц

| Файл | Үүрэг |
|------|-------|
| `app.py` | Streamlit веб интерфэйс (газрын зураг, дэлгэрэнгүй, MILP, станц сонголт) |
| `solar.py` | Нарны систем + батарей + өртгийн энгийн тооцоо (Load-factor) |
| `capacity.py` | Шугамын нэвтрүүлэх чадвар (дулаан/хүчдэлийн уналт/SIL) |
| `network.py` | Өгөгдөл унших, граф, төвлөрсөн/тархмал зөвлөмж |
| `profiles.py` | Цаг тутмын эрэлтийн профайл (4 улирлын төлөөлөх өдөр) |
| `pvgis.py` | PVGIS API-аас нарны үйлдвэрлэл + офлайн загвар |
| `optimize.py` | Block 3 MILP оновчлол (grid + LinDistFlow) |
| `mapbuilder.py` | Folium газрын зураг |
| `generate_map.py` | Статик HTML гаргах CLI |
| `soums_v2.xlsx`, `lines_v2.xlsx`, `soum_load_profile.xlsx` | Эх өгөгдөл |
| `icon1.png` | Нарны станцын тэмдэглэгээний зураг |
