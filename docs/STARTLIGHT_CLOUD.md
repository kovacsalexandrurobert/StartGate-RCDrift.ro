# Start Light — protocol 2, sincronizat cu RCDrift

Firmware-ul și site-ul folosesc un singur pas de concurs. Clientul asociat folosește implicit **https://staging.rcdrift.ro**. Nu se schimbă automat destinația spre producție și nu se copiază credențiale pe PC sau în Git.

## Ce apasă organizatorul

1. Salvează pregătirea și pornește calificările în RCDrift. Împerechează Pico folosind codul din Configurare semafor. Instalează toate modulele noi `.py` înainte de împerechere; protocolul vechi este blocat pentru conducerea sincronizată.
2. Un singur buton principal afișează **START**, apoi așteaptă confirmarea verdelui/stingerii lămpilor și notele arbitrilor. După toate notele, același buton devine **Următorul pilot**. Următorul pilot nu pornește singur: încă o apăsare când este pregătit trimite START.
3. Toți piloții fac manșa 1, apoi manșa 2. În dueluri: prezentare → START prima rulare → pregătirea pozițiilor inversate → START a doua rulare → votare → duelul următor. Completul, corecturile și rezultatele rămân gestionate de RCDrift.
4. START-ul din pagina locală și intrarea opțională GPIO folosesc aceeași comandă. Un dispozitiv nu poate publica puncte, administra roluri sau relua singur un concurs pus în pauză.

## Pauză, conexiune și repornire

- Pauza invalidează START-urile neexecutate. În secvență, firmware-ul verifică periodic pasul/permisiunea și oprește lămpile la pauză, schimbarea sesiunii sau pierderea lease-ului de 5 secunde. Timpul de rețea/DNS/firmware nu este o garanție de oprire în timp real; aceasta nu este o instalație de oprire de urgență.
- Confirmarea `stopped` se trimite numai după `all_off()`. RCDrift păstrează pauza, pilotul, manșa și notele. Reluarea cere confirmarea stingerii și nu pornește automat o nouă secvență.
- La repornire, Pico persistă un contor în `cloud_state.json`, oprește lămpile și sincronizează sesiunea înainte de comenzi. Un contor vechi, o comandă deja preluată ori o apăsare retrimisă nu pot porni din nou lămpile.
- În modul împerecheat nu există fallback START prin HTTP/BLE când site-ul nu poate confirma. Pentru folosire independentă, dezleagă explicit dispozitivul; modul standalone își păstrează secvența unică și reglajele.
- `done` confirmă **stingerea lămpilor**, nu sosirea mașinii. Senzorul IR rămâne opțional, dezactivat implicit; `finish` nu schimbă singur pilotul sau notele.

## Buton pe cutie

În sursa inițială nu este definit un pin START. `PHYSICAL_BUTTON_PIN = None` rămâne dezactivat până la cunoașterea cablajului. Pentru un buton cablat la GND configurează explicit un pin liber; codul folosește pull-up, debounce și cere eliberare după boot. Nu folosi GP2–GP5, GP6/GP7 sau pinul senzorului. Butonul START din pagina locală funcționează fără cablaj GPIO suplimentar.

## Transport

Protocolul 2 folosește tokenul dispozitivului și numai evenimentul/categoria împerecheate. Poll-ul conține revizia, pasul, STOP/sync, comanda atribuită acestui dispozitiv și lease-ul. `claim` cere sesiunea curentă și returnează `claimed: true` o singură dată. `events` primește `sync`, `stopped`, `go`, `done` și evenimentele opționale de senzor; confirmările vechi sunt respinse. `button` folosește `requestId` stabil pentru retrimitere, fără dublare.

HTTPS verifică CA și hostname; nu există fallback CERT_NONE. `root_ca.py` conține numai certificatul public ISRG Root X1, iar `ntptime.py` inițializează ceasul UTC dacă este necesar. Dacă hostingul schimbă autoritatea de certificare, actualizează CA după verificare. Nu copia CA-ul unui antivirus de pe PC. Referințe: [MicroPython SSL](https://docs.micropython.org/en/v1.26.0/library/ssl.html), [ISRG](https://letsencrypt.org/certificates/), [NTP de referință](https://github.com/micropython/micropython-lib/tree/master/micropython/net/ntptime).

## Instalare și probe

Copiază numai `firmware/*.py` în rădăcina Pico. Păstrează fișierele WiFi/reglaje/token de pe dispozitiv; arhiva de sursă nu le conține. Nu instala UF2 de alt model. Vezi [DEPLOY](DEPLOY.md).

`python -m unittest discover -s tests -v` folosește GPIO/ceas/transport simulate și codul real de secvență/coordonare. `python tests/staging_tls_smoke.py` verifică numai HTTPS public și versiunea staging, fără token sau acționare. Nu reprezintă o probă electrică pe Pico, SSR, lămpi sau senzor; aceasta se face după încărcarea firmware-ului pe dispozitivul conectat.
