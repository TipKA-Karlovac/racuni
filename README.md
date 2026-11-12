# racuni

[![CI](https://github.com/TipKA-Karlovac/racuni/actions/workflows/ci.yml/badge.svg)](https://github.com/TipKA-Karlovac/racuni/actions/workflows/ci.yml)

Ponude i računi za obrtnike i male tvrtke: klijenti, stavke, izdavanje s
rednim brojem, PDF s barkodom za plaćanje i pregled onoga što još nije
naplaćeno.

*English summary: quotes and invoices for small Croatian businesses. Django
REST API + React front end. Gapless numbering, immutable issued documents,
exact decimal arithmetic, PDF output with a HUB-3A payment barcode.*

> **Važno:** ovo je primjer za portfolio, a ne certificirani program za
> izdavanje računa. Ne fiskalizira račune i ne šalje eRačune, pa se u ovom
> obliku ne smije koristiti za izdavanje računa koji podliježu fiskalizaciji.
> Tekst napomene o PDV-u u primjeru podataka je ilustracija, a ne porezni
> savjet.

## Što radi

- **Klijenti** – evidencija s provjerom OIB-a; klijent s dokumentima se ne
  briše, nego arhivira
- **Ponude i računi** – nacrt sa stavkama (količina, jedinica, cijena, popust,
  po potrebi PDV), s iznosima koji se računaju dok tipkate
- **Izdavanje** – dokument dobiva sljedeći redni broj i današnji datum
- **Ponuda → račun** – iz izdane ili prihvaćene ponude nastaje nacrt računa s
  istim stavkama
- **PDF** – ponuda ili račun na A4; izdani račun ima podatke za plaćanje i 2D
  barkod koji se skenira bankarskom aplikacijom
- **Pregled** – nenaplaćeno, što kasni, izdano ove godine, ponude bez odgovora

## Pravila koja aplikacija čuva

Ovo je dio koji razlikuje evidenciju računa od obične tablice.

**Brojevi idu redom, bez rupa i bez duplikata.** Nacrt nema broj. Broj se
dodjeljuje tek pri izdavanju, unutar transakcije koja zaključava brojač, pa
dva istodobna izdavanja ne mogu dobiti isti broj. Ako izdavanje ne uspije,
broj se ne troši. Kao zadnja obrana, baza ima jedinstveno ograničenje na
(vrsta, godina, redni broj). Brojanje kreće ispočetka svake godine.

**Izdani dokument se ne mijenja.** Može se samo stornirati; broj storniranog
dokumenta ostaje zauzet. Nacrt se slobodno uređuje i briše.

**Podaci kupca se prepisuju u dokument.** Ako klijent kasnije promijeni naziv
ili adresu, već izdani računi ostaju kakvi su bili.

**Datum izdavanja je uvijek današnji**, pa brojevi idu istim redom kao datumi.

**Novac se računa točno.** Svi iznosi su `Decimal`, a u JSON-u putuju kao
tekst – nikad kao decimalni broj s pomičnim zarezom. Iznos stavke zaokružuje
se na cent; PDV se računa na osnovicu po stopi, a ne po stavci. Pregled u
pregledniku računa isto, u cijelim brojevima (`BigInt`), i testiran je na
istim primjerima kao poslužitelj.

**Tko nije u sustavu PDV-a, ne iskazuje PDV.** Stopa na stavkama se tada
zanemaruje i na poslužitelju, ne samo u sučelju.

## Barkod za plaćanje

Izdani račun nosi PDF417 barkod prema uputi Hrvatske udruge banaka *Format
zapisa 2D barkoda prema HUB-3 standardu*, verzija 6: 9 podatkovnih stupaca,
razina ispravljanja pogreške 4, binarno kodiranje u UTF-8, modul širine
0,254 mm. Poziv na broj je broj računa (npr. `HR00 12-1-1`).

Barkod je provjeren čitanjem neovisnim čitačem (ZXing). Skeniranje stvarnom
bankarskom aplikacijom nije provjereno.

## Tehnologije

| Dio | Tehnologije |
|---|---|
| Backend | Python, Django 5.2, Django REST framework, ReportLab |
| Baza | PostgreSQL (produkcija), SQLite (razvoj) |
| Frontend | React 19, React Router, Vite |
| Kvaliteta | pytest, Vitest, Ruff, ESLint, GitHub Actions |

## Pokretanje na svom računalu

Potrebni su Python 3.11+ i Node 20+.

**Backend** (Windows PowerShell):

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
$env:DJANGO_DEBUG = "1"
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py seed_demo --owner vlasnik
.venv\Scripts\python manage.py changepassword vlasnik
.venv\Scripts\python manage.py runserver 8001
```

Na Linuxu i macOS-u umjesto `.venv\Scripts\` pišite `.venv/bin/`, a varijablu
postavite s `export DJANGO_DEBUG=1`.

`seed_demo` upisuje izmišljenog izdavatelja, dva klijenta, jednu ponudu i dva
računa. OIB i IBAN u primjeru imaju ispravne kontrolne znamenke, ali ne
pripadaju nikome.

**Frontend** (u drugom prozoru):

```powershell
cd frontend
npm install
npm run dev
```

Aplikacija je na <http://localhost:5174>.

## Testovi

```powershell
cd backend
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check .

cd ..\frontend
npm test
npm run lint
```

Testovi pokrivaju izračun iznosa i zaokruživanje, numeraciju (redoslijed, nova
godina, neuspjelo izdavanje, duplikat u bazi), sva pravila o stanju dokumenta,
cijeli API s pravima pristupa i CSRF zaštitom te sadržaj PDF-a.

## Što (još) nije uključeno

- fiskalizacija i eRačun
- slanje dokumenta e-poštom izravno iz aplikacije
- djelomična plaćanja i knjiženje uplata
- više korisnika s različitim pravima
- upute za postavljanje na poslužitelj

## Licenca

[MIT](LICENSE)
