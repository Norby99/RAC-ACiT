# Ratchet & Clank: A Crack in Time — port europeo (BCES00511)

Ricompilazione statica per Windows della versione **europea** di *Ratchet & Clank: A Crack in Time*
(in italiano *A Spasso nel Tempo*), a partire dal dump del gioco preso dalla mia PS3 moddata.

## Obiettivo

[RACiT](https://github.com/HighDrexler/RACiT) porta il gioco su PC con
[ps3recomp](https://github.com/sp00nznet/ps3recomp), ma parte dalla versione americana (`BCUS98124`),
che non ha tutte le lingue. Voglio la stessa cosa partendo dalla mia copia `BCES00511`, così da avere
tutte le lingue del disco europeo. L'italiano è la priorità.

RACiT è il riferimento e la base da cui partire, non codice da riusare alla cieca: è costruito attorno
a un altro eseguibile, quindi hook, patch e ottimizzazioni **vanno considerati rotti finché non sono
verificati** sulla mia versione.

## Stato attuale

Il progetto è un repository git solo locale: `main` parte dalla storia di RACiT (commit `92656ee`, remote
`racit`), non è una fork su GitHub e non ha ancora commit miei. La toolchain è in `tools/`, con ps3recomp già patchato. Gli indirizzi sono stati convertiti a BCES00511 (modifiche non
committate). Il lift PPU e `patch_lift.py` girano sul mio ELF; lift SPU, compilazione ed esecuzione sono
ancora da provare.

Aggiornamento: pipeline e compilazione riuscite (`game/build-win/game/RaCACiT.exe`). In un test di 60 s
il gioco parte, carica `front_end` e presenta circa 60 frame al secondo secondo i log, ma nessuno ha ancora
guardato lo schermo né provato i comandi o un livello.

Aggiornamento: provato a mano in italiano con `run.bat`, l'utente conferma che funziona tutto.
La lingua si sceglie in `run.bat` (tabella in `README_LINGUE.md`).

Obiettivo successivo: provare su Linux la build nativa, senza Proton. Script e istruzioni sono in `LINUX.md`,
`linux/`, `scripts/setup_linux.sh`, `scripts/build_linux.sh` e `run.sh`. La prova con zig da Windows compila
tutto e al link mancano solo i simboli SDL2, assenti nella prova. Non è mai stata avviata su Linux.
La cache del gioco ora va in `PS3_HDD1_ROOT` (`analysis/run/hdd1`), fuori dal dump: verificato su Windows.

Per avviarlo a mano: `PS3_VFS_ROOT=<percorso>/dev/BCES00511`, `PS3_HDD0_ROOT=analysis/run/hdd0`,
`RACACIT_LOG_FILE=analysis/run/game.log`, con `dev/EBOOT.ELF` come argomento.
Attenzione: `map_cellfs_devices` in `game/main.cpp` mappa `/dev_hdd1/` sulla stessa radice del disco, quindi
il gioco crea `cache/BCES00511/` dentro il dump. Va rimappata fuori da `dev/` prima dei prossimi test.

La mappa è in `scripts/addr_map_usa_eu.tsv`, generata da `scripts/dev/port_addresses.py` (uso una tantum
sui sorgenti USA: non rilanciarlo). Il codice si sposta a blocchi da `+0x0` a `+0x628`, il codice SPU di
`+0x800`, dati finali e bss di `+0x100`, il pool vicino a `0xD2F...` di `+0xC0`.
Verificati sul mio ELF: 43 funzioni Lua per nome, tutte le funzioni citate da `stubs.cpp` e
`patch_lift.py` esistono, le 27 patch si applicano e 760 righe di `spu_submodules.txt` cadono su un job.
Dedotti senza prova diretta: `0xF5D780` (camera), `0xE24F78` (arma), `0xD2FA48` (solo diagnostica).
Da controllare: `func_0066CB18` è la lista lingue e la patch 15 forza gli indici 4-6, scelti per il disco
americano. Le stringhe `BCUS98124` del launcher e gli asset delle lingue non sono ancora adattati.

- `dev/EBOOT.ELF`: `EBOOT.BIN` decriptato, 14.515.408 byte, SHA-256
  `6debdca0f181f35d98ebe23faabe2531b697c558b4e3384b06630173400674c1`.
- `dev/libsre.prx`: da `dev_flash/sys/external/libsre.sprx` del firmware 4.91, SHA-256
  `ddfdaff53847b4b878c58299c2727d4e834cf6d6e8c12c62a58d13ab13b08871`.
  `lift_libsre.py` non ha indirizzi fissi di una specifica versione della libreria, ma non sappiamo
  quale firmware abbia usato RACiT: se SPURS si comporta in modo strano, tenerlo presente.
- `dev/BCES00511/`: il dump del gioco.
- `dev/PS3UPDAT.PUP`: firmware PS3 (206 MB, intestazione valida), per ora non serve.

## Il dump: `dev/BCES00511/`

| | |
| --- | --- |
| Title ID | `BCES00511`, `APP_VER` 01.00, `VERSION` 01.00, firmware minimo 3.01 |
| Dimensione | 24 GB, 811 file |
| `PS3_GAME/USRDIR/EBOOT.BIN` | 14,5 MB, **SELF criptato** (inizia con `SCE\0`) |
| SHA-256 di `EBOOT.BIN` | `0d3c7e78fc66a8f964fbaab9d90436b717a8f60ec999f1245d1134131e7e9f83` |
| `USRDIR/built/` | 8,8 GB: filmati Bink (`.bik`) e `.pkg` per lingua in `movies/<nome>/` |
| `USRDIR/packed/` | 15 GB: `.psarc` globali in `game/`, `level_cached` e `level_uncached` per 22 livelli in `levels/` |
| Trofei | `PS3_GAME/TROPDIR/NPWR00941_00/TROPHY.TRP` |
| `PS3_UPDATE/PS3UPDAT.PUP` | Aggiornamento firmware del disco, esattamente 256 MiB: controllare che sia valido prima di usarlo |

I `.pkg` dei filmati esistono con 15 suffissi: `us gb fr es de it nl dk se no fi pt jp kr cn`.
Alcuni filmati hanno anche varianti `.bik` dedicate (`_esp`, `_ita`, `_jpn`, `_uk`).
I suffissi non provano che ogni lingua abbia testo e doppiaggio completi: va verificato sui dati.

`dev/BCES00511/` è di sola lettura: nessuno strumento deve modificarla.

## Pipeline di RACiT

Da `BUILDING.md` e `scripts/`, in Git Bash:

1. `scripts/setup_windows.sh` scarica in `tools/` zig, cmake, ninja e i sorgenti alle versioni fissate,
   e applica `patches/ps3recomp-0001-racacit-runtime-fixes.patch` a ps3recomp
   (commit `5244db92669b54831c6d3ebb7a96d58c4dbfa6df`).
2. `scripts/pipeline.sh` genera il codice in `game/src/recomp` e `game/spu`:
   `ppu_loader` → nomi Ghidra (opzionali) → `ppu_lifter` → `patch_lift.py` → estrazione e lift SPU
   (`lift_libsre.py`, `lift_policy_modules.py`, `lift_spu_jobs.py`) → di nuovo `patch_lift.py`.
3. `cmake -S windows -B game/build-win ...` con la toolchain zig, poi `cmake --build game/build-win -j6`.
4. `launcher/build.sh` compila il launcher.

Input richiesti in `dev/` (RACiT originale usa `input/`, qui i percorsi sono già cambiati):

- `EBOOT.ELF`: `EBOOT.BIN` decriptato, ad esempio con RPCS3 (Utilities > Decrypt PS3 Binaries).
- `libsre.prx`: decriptato da `dev_flash/sys/external/libsre.sprx` del firmware.

Il comando esatto del passo 3 è in `BUILDING.md` di RACiT.

## Cosa dipendeva dalla versione americana

Tabella del lavoro di conversione: resta utile per sapere dove stanno gli indirizzi, ma quelli dei
sorgenti sono già convertiti, a parte il launcher.
Gli indirizzi dell'eseguibile americano **non valgono** per il mio, salvo verifica byte per byte.
Vale per ogni `func_XXXXXXXX`, ogni `0x...` di codice o dati e ogni offset di struttura.

| Dove (in RACiT) | Cosa contiene | Cosa fare |
| --- | --- | --- |
| `scripts/patch_lift.py` | Patch sul codice generato, cercate per nome di funzione e per testo esatto | Ritrovare ogni funzione; aggiungere errori espliciti se un punto non viene trovato |
| `game/stubs.cpp` | Hook, override HLE, globali e layout del gioco | Riportare gli indirizzi uno per uno, tenendo solo ciò che serve |
| `game/main.cpp`, `game/button_prompts.cpp` | Title ID `BCUS98124`, indirizzi nelle parti specifiche del gioco | Aggiornare e verificare |
| `patches/ps3recomp-…-runtime-fixes.patch` | 1,9 MB su 86 file: renderer Vulkan, audio, SPU, input | Generico in gran parte, ma ha riferimenti a funzioni del gioco da controllare |
| `scripts/lift_spu_jobs.py` | Intervallo di scansione `0xAD9780..0xBE3C80`, `ELF_OVERLAYS`, altri indirizzi nell'EBOOT | Ricalcolare sul mio ELF |
| `scripts/lift_policy_modules.py`, `lift_libsre.py`, `name_pass.py`, `ppc_scan.py`, `fix_vmx_alias.py` | Indirizzi fissi | Controllare uno per uno |
| `scripts/spu_submodules.txt` | Indirizzi EBOOT dei moduli SPU e relativi GUID | Rigenerare con `SPU_DUMP_JOBS` e `find_submodules.py` |
| `scripts/spu_starts.txt` | Coppie GUID e indirizzo di local store | Probabilmente riusabile se i job SPU sono identici: va dimostrato |
| `game/hot_ppu.h`, `hot_spu*` | Ottimizzazione: raggruppa il codice usato spesso | Partire vuoti e rigenerare alla fine con `scripts/dev/hot_funcs.py` |
| `launcher/src/store.cpp` | Controllo `BCUS98124`, SHA-256 dell'ELF americano, cartelle dei salvataggi | Passare a `BCES00511` e al mio hash |

### Lingue

In RACiT il gioco non ha un menu lingua: legge la lingua di sistema con
`cellSysutilGetSystemParamInt`. `RACACIT_LANGUAGE` (`game/stubs.cpp`) sostituisce quella risposta, e la
patch 15 di `patch_lift.py` sblocca nell'eseguibile americano le lingue escluse (`func_0066C518`).
Nel mio eseguibile la lista delle lingue ammesse sarà probabilmente diversa: va letta prima di decidere
se serve una patch. Il selettore del launcher va esteso a tutte le lingue davvero presenti.

### Gli hook sono funzioni aggiuntive, non requisiti

Separare sempre ciò che serve al gioco per funzionare (setjmp/longjmp per Lua, attese GPU, fix FIFO,
kick SPU, alias VMX) dagli extra (FOV e camera, skin armatura, salto filmati, ombre, Discord, DualSense,
prompt dei pulsanti). Prima il gioco deve avviarsi e arrivare in gioco; gli extra si riportano dopo.

## Piano di lavoro

1. ~~Ottenere `EBOOT.ELF` e `libsre.prx`.~~ Fatto.
2. ~~Importare RACiT qui, inizializzare git e installare la toolchain.~~ Fatto (compilata finora solo SDL2).
3. ~~Scrivere la tabella `indirizzo USA → indirizzo EU` e convertire i sorgenti.~~ Fatto.
4. Far girare tutta la pipeline, compreso il lift SPU.
5. Compilare e arrivare al menu principale, poi a un livello.
6. Riportare le correzioni necessarie, una alla volta, verificando ciascuna.
7. Abilitare la selezione delle lingue e provare l'italiano (testo, doppiaggio, filmati, sottotitoli).
8. Riportare gli extra, rigenerare le liste `hot_*`, adattare il launcher.

## Regole

- Tutti i file del gioco e della PS3 stanno in `dev/`, mai altrove. `dev/` è ignorata da git; attenzione
  a non confonderla con `scripts/dev/`, che è codice del progetto.
- **Mai committare o pubblicare codice di gioco generato**: violerebbe il copyright. Vale per `dev/`,
  `out/`, `analysis/`, `game/src/recomp/`, `game/spu/`, `game/prx/`, `game/build*/`, per binari e asset.
  Prima di ogni commit controllare l'elenco dei file. `tools/` resta ignorato. Nel repository vanno solo
  sorgenti scritti a mano e script: il codice del gioco si rigenera dalla copia di ciascuno.
- Mai modificare a mano il codice generato: ogni correzione passa da `patch_lift.py` o da `game/`, così
  sopravvive a un nuovo lift.
- Le modifiche al runtime in `tools/ps3recomp` vanno salvate nel file patch, come spiegato in `BUILDING.md`.
- Una patch che non trova il suo bersaglio deve **fermare il build**, non saltare in silenzio. In RACiT
  molti passi usano `if sp and ...`: sulla mia versione un indirizzo sbagliato sparirebbe senza errori.
- Trovare le funzioni per contenuto (sequenze di istruzioni, stringhe, riferimenti, tabelle Lua), non
  assumendo uno scostamento fisso dagli indirizzi americani.
- Mantenere le licenze MIT di RACiT e ps3recomp e dire chiaramente che questo è un derivato non ufficiale.

## Ambiente

Windows 11, 32 GB di RAM (il build `-j6` di RACiT ne chiede circa 32: se serve, abbassare `-j`).
Disponibili Git Bash, git, Python 3.13 e RPCS3 in `F:\ProgramFiles\RPCS3` (firmware 4.91 installato).

- Python: si usa la 3.13, anche se RACiT chiede la 3.12. `setup_windows.sh` cerca `py -3.12`, quindi va
  lanciato con `PYTHON=python`: così installa i pacchetti fissati e compila SDL2 senza errori. La
  pipeline di lift su 3.13 è ancora da provare; installare la 3.12 solo se fallisce.
- RPCS3: non lanciarlo da riga di comando con `--help`, perché non termina e la shell resta bloccata.
- cmake, ninja e zig non vanno installati a parte: li porta `setup_windows.sh` in `tools/`.

## Riferimenti

- RACiT: <https://github.com/HighDrexler/RACiT> (`BUILDING.md`, commenti di `patch_lift.py` e `stubs.cpp`)
- ps3recomp: <https://github.com/sp00nznet/ps3recomp>, branch `master`
  (`docs/GAME_PORTING_GUIDE.md`, `docs/GETTING_STARTED.md`)
