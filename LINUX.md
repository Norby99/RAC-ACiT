# Build nativa per Linux

Build nativa, senza Proton o Wine. **Non è ancora stata avviata su Linux.** Da Windows il codice è stato
compilato per Linux con zig: tutti i sorgenti compilano e al link mancano solo i simboli di SDL2, che nella
prova non era presente. Avvio, video, audio e controller sono da verificare.

## Cosa serve

- CPU x86-64 con AVX2, FMA e BMI2
- GPU con driver Vulkan funzionanti
- Circa 32 GB di RAM per compilare con 6 job paralleli
- `clang`, Python 3, git, pkg-config e i file di sviluppo di SDL2

| Distribuzione | Comando |
| --- | --- |
| Debian, Ubuntu | `sudo apt install clang git python3-venv pkg-config libsdl2-dev libvulkan1` |
| Fedora | `sudo dnf install clang git python3 pkgconf-pkg-config SDL2-devel vulkan-loader` |
| Arch | `sudo pacman -S clang git python pkgconf sdl2 vulkan-icd-loader` |

Su Arch recenti, se `sdl2` viene sostituito da `sdl2-compat`, la build dovrebbe funzionare allo stesso modo.
Su sistemi immutabili (Bazzite, SteamOS) conviene compilare in un container, per esempio con distrobox.

## Cosa copiare da Windows

Copia l'intera cartella del progetto, tranne le parti che si rigenerano.

| Da copiare | Da non copiare |
| --- | --- |
| Il repository, compresa `.git` | `tools/` |
| `dev/` | `game/build-win/`, `game/src/recomp/`, `game/spu/`, `game/prx/` |
| `analysis/run/hdd0`, per tenere salvataggi e trofei | `out/` e il resto di `analysis/` |

## Compilare

```bash
bash scripts/setup_linux.sh
```

```bash
bash scripts/build_linux.sh
```

Con meno di 32 GB di RAM indica meno job, per esempio `bash scripts/build_linux.sh 3`.

## Avviare

```bash
bash run.sh
```

La lingua si cambia nella riga `LINGUA=it` di `run.sh`. La tabella è in [README_LINGUE.md](README_LINGUE.md).

## Se qualcosa non funziona

Il log è in `analysis/run/game.log`. Cose da controllare per prime:

- la sezione Vulkan del log, se la finestra non si apre;
- le cartelle di `analysis/run/`, che devono ricevere salvataggi e cache al posto di `dev/`;
- la velocità: alcune ottimizzazioni del build e diverse diagnostiche esistono solo su Windows, quindi
  su Linux il gioco potrebbe andare più lento.

In ultima istanza l'eseguibile Windows può girare con Proton o Wine, ma non è l'obiettivo.
