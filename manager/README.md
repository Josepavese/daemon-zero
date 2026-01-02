# AgentZero Manager 🤖

**Manager All-in-One per istanze Docker di [AgentZero](https://github.com/frdel/agent-zero).**
Questo tool permette di gestire facilmente il ciclo di vita degli agenti, la configurazione e i file, offrendo sia una **Interfaccia Grafica (GUI)** che una **Riga di Comando (CLI)**.

---

## 🚀 Guida Rapida

### 1. Installazione
Prepara il sistema (installa Docker se necessario, configura i permessi e crea le cartelle):
```bash
./install.sh
```
*Nota: Se è la prima volta che installi Docker, potrebbe essere necessario riavviare il computer o fare logout/login.*

### 2. Avvio GUI
Il modo più semplice per gestire AgentZero è tramite l'interfaccia web.
```bash
python3 az-gui.py
```
> **Apri il browser su: [http://localhost:8080](http://localhost:8080)**

Dalla GUI puoi:
- **Creare/Eliminare istanze**: Ogni istanza è isolata.
- **Start/Stop**: Avvia e ferma i container.
- **Configurazione**: Modifica chiavi API (.env) e modelli (settings.json) direttamente dal browser.
- **File Browser**: Scarica i file generati dall'agente o carica documenti nel suo Workspace.
- **Logs**: Vedi cosa sta facendo l'agente in tempo reale.
- **Open WebUI**: Accedi all'interfaccia nativa di AgentZero (porta 50080+).

---

## 💻 CLI (Riga di Comando)

Se preferisci il terminale, usa lo script `az-manage` (o `python3 az_manage.py`).

| Comando | Descrizione |
|---------|-------------|
| `az-manage list` | Mostra tutte le istanze, il loro stato e la porta. |
| `az-manage start [nome]` | Avvia un'istanza. Se non esiste, la crea. |
| `az-manage stop [nome]` | Ferma un'istanza attiva. |
| `az-manage delete [nome]` | Elimina il container. Aggiungi `--data` per cancellare anche i file. |
| `az-manage logs [nome]` | Mostra i log del container (Ctrl+C per uscire). |

**Esempi:**
```bash
# Avvia un agente chiamato 'dev-bot'
./az-manage start dev-bot

# Avvia un agente effimero (nessun salvataggio dati alla chiusura)
./az-manage start test-veloce --ephemeral

# Lista agenti
./az-manage list
```

---

## 📂 Struttura Dati

AgentZero Manager organizza i dati nella tua home directory per garantire la persistenza tra riavvii.

**Percorso Base:** `~/agent-zero/`

Ogni istanza (es. `my-agent`) avrà la sua sottocartella in `~/agent-zero/my-agent/`:
- 📁 **config/**: Contiene `.env` e file di configurazione temporanei.
- 📁 **workspace/**: Area di scambio file. Qui trovi i file generati dall'agente.
- 📁 **memory/**: Memoria a lungo termine (vettoriale e JSON).
- 📁 **knowledge/**: Documenti caricati per la RAG.

> **Nota Tecnica**: All'interno del container Docker, la cartella `workspace` locale viene montata su `/a0/workspace`. L'agente è configurato per usare questo percorso come directory di lavoro.

---

## 🛠 Sviluppo & Build

Per aggiornare o modificare il manager:

1. Modifica i file sorgente (`az-gui.py`, `templates/index.html`).
2. Riavvia semplicemente lo script python per testare.
3. (Opzionale) Compila un eseguibile standalone:
```bash
./build.sh
```
L'eseguibile verrà creato in `dist/agent-zero-manager`.

---

*Creato per semplificare l'orchestrazione locale di agenti AI autonomi.*
