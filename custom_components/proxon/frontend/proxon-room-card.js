/*
 * Proxon room cards for Home Assistant (shipped with the "HA Proxon FWT 2.0 Modbus" integration).
 *
 *   type: custom:proxon-room-card        # "Proxon Karte (detailliert)"
 *   type: custom:proxon-room-card-slim   # "Proxon Karte (kompakt)"
 *   entity: climate.buero                # the room's climate entity (required)
 *   name: Büro                           # optional
 *   # optional overrides (normally found automatically on the same device):
 *   heating: switch.buero_heizelement    # PTC enable switch
 *   status: binary_sensor.buero_heizelement_status
 *   lock: switch.buero_sperren_bedienteil
 *   humidity: sensor.proxon_luftfeuchte_wohnzimmer
 *
 * PTC icon: grey = off, orange = enabled, red = heating.
 * Clicks on -/+ are collected and sent as one write after a short pause.
 */
(() => {
  const VERSION = "3";
  const SEND_DELAY_MS = 600; // wait for further -/+ clicks before writing the register
  const PENDING_MAX_MS = 15000; // stop showing the local value if the state never follows

  const TK = {
    heating: "proxon_zone_heizelement",
    status: "proxon_zone_heizelement_status",
    lock: "proxon_zone_tastensperre",
  };

  const CSS = `
    :host { display: block; }
    ha-card { padding: 12px 16px; }
    ha-icon { --mdc-icon-size: 24px; }
    .head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .name { font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .head .name { font-size: 1.1em; }
    .temps { display: flex; align-items: center; gap: 12px; margin: 8px 0 4px; }
    .ist { font-size: 2.2em; font-weight: 700; line-height: 1.1; }
    .hum { color: var(--secondary-text-color); display: inline-flex; align-items: center; }
    .row { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 8px; }
    .label { color: var(--secondary-text-color); }
    .pill { display: inline-flex; align-items: center; border-radius: 20px;
      background: var(--secondary-background-color, #eee); }
    .pill .val { min-width: 3.2em; text-align: center; font-weight: 500; }
    button { cursor: pointer; border: none; background: transparent; color: var(--primary-text-color);
      border-radius: 50%; width: 36px; height: 36px; display: inline-flex; align-items: center;
      justify-content: center; padding: 0; }
    button[disabled] { opacity: 0.4; cursor: default; }
    button.ptc { background: var(--secondary-background-color, #eee); }
    .chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 16px;
      background: var(--secondary-background-color, #eee); cursor: pointer; }
    .chip.static { cursor: default; }
    .compact { display: flex; align-items: center; gap: 10px; }
    .compact .info { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; }
    .compact .name { font-size: 1em; }
    .compact .sub { color: var(--secondary-text-color); font-size: 0.9em; }
    .compact .ptc-icon { display: inline-flex; width: 36px; height: 36px; align-items: center; justify-content: center; }
    .unavailable { opacity: 0.5; }
  `;

  const esc = (v) =>
    String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const GREY = "var(--disabled-text-color, #9e9e9e)";
  const ORANGE = "var(--warning-color, #ff9800)";
  const RED = "var(--error-color, #db4437)";

  class ProxonRoomCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._slim = false;
      this._pending = undefined; // temperature chosen with -/+ but not yet confirmed by the state
      this._sent = false;
      this._timer = null;
      this._expires = 0;
    }

    setConfig(config) {
      if (!config || !config.entity) {
        throw new Error("Bitte 'entity' (die climate-Entität des Raums) angeben.");
      }
      this._config = config;
      this._ids = null;
    }

    set hass(hass) {
      this._hass = hass;
      this._render();
    }

    getCardSize() {
      return this._slim ? 1 : 4;
    }

    disconnectedCallback() {
      if (this._timer) {
        clearTimeout(this._timer);
        this._timer = null;
      }
    }

    static getConfigForm() {
      return {
        schema: [
          { name: "entity", required: true, selector: { entity: { domain: "climate", integration: "proxon" } } },
          { name: "name", selector: { text: {} } },
        ],
      };
    }

    static getStubConfig(hass) {
      const climate = Object.keys(hass.entities || {}).find(
        (id) => id.startsWith("climate.") && hass.entities[id].platform === "proxon"
      );
      return { entity: climate || "climate.example" };
    }

    // Find the room's sibling entities on the same device (by translation key).
    _resolve() {
      if (this._ids) return this._ids;
      const hass = this._hass;
      const cfg = this._config;
      const ids = { heating: cfg.heating, status: cfg.status, lock: cfg.lock, humidity: cfg.humidity };
      const device = hass.entities && hass.entities[cfg.entity] && hass.entities[cfg.entity].device_id;
      if (device) {
        for (const ent of Object.values(hass.entities)) {
          if (ent.device_id !== device) continue;
          for (const key of ["heating", "status", "lock"]) {
            if (!ids[key] && ent.translation_key === TK[key]) ids[key] = ent.entity_id;
          }
          if (!ids.humidity && ent.entity_id.startsWith("sensor.")) {
            const st = hass.states[ent.entity_id];
            if (st && st.attributes.device_class === "humidity") ids.humidity = ent.entity_id;
          }
        }
      }
      this._ids = ids;
      return ids;
    }

    _state(id) {
      return id ? this._hass.states[id] : undefined;
    }

    _call(domain, service, data) {
      this._hass.callService(domain, service, data);
    }

    // -/+ : change the shown target immediately, write the register once clicks stop.
    _step(direction) {
      const st = this._state(this._config.entity);
      if (!st) return;
      const a = st.attributes;
      const step = a.target_temp_step || 0.5;
      const base = this._pending !== undefined ? this._pending : Number(a.temperature);
      if (Number.isNaN(base)) return;
      let next = Math.round((base + direction * step) / step) * step;
      if (a.min_temp !== undefined) next = Math.max(next, a.min_temp);
      if (a.max_temp !== undefined) next = Math.min(next, a.max_temp);
      if (next === base) return;
      this._pending = next;
      this._sent = false;
      this._expires = Date.now() + SEND_DELAY_MS + PENDING_MAX_MS;
      if (this._timer) clearTimeout(this._timer);
      this._timer = setTimeout(() => {
        this._timer = null;
        this._sent = true;
        this._call("climate", "set_temperature", { entity_id: this._config.entity, temperature: this._pending });
      }, SEND_DELAY_MS);
      this._render();
    }

    _toggle(id) {
      const domain = id.split(".")[0];
      this._call(domain, "toggle", { entity_id: id });
    }

    _num(value, decimals) {
      const n = Number(value);
      return Number.isNaN(n) ? "–" : n.toFixed(decimals).replace(".", ",");
    }

    _render() {
      if (!this._hass || !this._config) return;
      const cfg = this._config;
      const climate = this._state(cfg.entity);
      const root = this.shadowRoot;
      if (!climate) {
        root.innerHTML = `<ha-card><div class="unavailable">Entität nicht gefunden: ${esc(cfg.entity)}</div></ha-card>`;
        return;
      }
      const ids = this._resolve();
      const a = climate.attributes;
      const name = esc(cfg.name || a.friendly_name || cfg.entity);
      const unavailable = climate.state === "unavailable";

      // Local (not yet confirmed) target: drop it once the state caught up or took too long.
      if (this._pending !== undefined && this._sent) {
        const reported = Number(a.temperature);
        if (Math.abs(reported - this._pending) < 1e-6 || Date.now() > this._expires) {
          this._pending = undefined;
        }
      }

      const heatingSt = this._state(ids.heating);
      const statusSt = this._state(ids.status);
      const enabled = heatingSt ? heatingSt.state === "on" : climate.state === "heat";
      const heating = statusSt ? statusSt.state === "on" : false;
      // "off" is plain text colour on the compact card (grey would look disabled).
      const offColor = this._slim ? "var(--primary-text-color)" : GREY;
      const color = heating ? RED : enabled ? ORANGE : offColor;
      const label = heating ? "heizt" : enabled ? "freigegeben" : "aus";

      const sollValue = this._pending !== undefined ? this._pending : Number(a.temperature);
      const step = a.target_temp_step || 0.5;
      const decimals = step >= 1 ? 0 : 1;
      const ist = `${this._num(a.current_temperature, 1)} °C`;
      const min = a.min_temp;
      const max = a.max_temp;
      const atMin = min !== undefined && sollValue <= min;
      const atMax = max !== undefined && sollValue >= max;
      const hum = this._state(ids.humidity);
      const humText = hum && hum.state !== "unavailable" && hum.state !== "unknown" ? `${hum.state} %` : "";

      const sollText = this._slim
        ? this._num(sollValue, decimals)
        : `${this._num(sollValue, decimals)} °C`;
      const stepper = `
        <div class="pill">
          <button id="minus" ${atMin || unavailable ? "disabled" : ""}><ha-icon icon="mdi:minus"></ha-icon></button>
          <span class="val">${sollText}</span>
          <button id="plus" ${atMax || unavailable ? "disabled" : ""}><ha-icon icon="mdi:plus"></ha-icon></button>
        </div>`;
      const iconStyle = `color:${color}`;
      const ptcButton = ids.heating
        ? `<button class="ptc" id="ptc" title="Heizelement ${label}"><ha-icon icon="mdi:radiator" style="${iconStyle}"></ha-icon></button>`
        : `<span class="ptc-icon" title="Heizelement ${label}"><ha-icon icon="mdi:radiator" style="${iconStyle}"></ha-icon></span>`;

      let body;
      if (this._slim) {
        // Lock button only when the lock is writable (a switch, i.e. Modbus write level 2).
        const lockSwitch = ids.lock && ids.lock.startsWith("switch.") ? this._state(ids.lock) : undefined;
        const lockButton = lockSwitch
          ? `<button class="ptc" id="lock" title="Bedienteil ${lockSwitch.state === "on" ? "gesperrt - freigeben" : "frei - sperren"}"><ha-icon icon="${
              lockSwitch.state === "on" ? "mdi:lock" : "mdi:lock-open-variant"
            }"></ha-icon></button>`
          : "";
        body = `
          <div class="compact ${unavailable ? "unavailable" : ""}">
            <div class="info">
              <span class="name">${name}</span>
              <span class="sub">${ist}</span>
            </div>
            ${lockButton}
            ${stepper}
            ${ptcButton}
          </div>`;
      } else {
        const lockSt = this._state(ids.lock);
        let lockRow = "";
        if (lockSt) {
          const locked = lockSt.state === "on";
          const writable = ids.lock.startsWith("switch.");
          lockRow = `
            <div class="row">
              <span class="label">Bedienteil</span>
              <span class="chip ${writable ? "" : "static"}" id="lock"
                title="${writable ? "Sperren / freigeben" : "Nur Anzeige (Modbus-Schreibrecht 2 nötig)"}">
                <ha-icon icon="${locked ? "mdi:lock" : "mdi:lock-open-variant"}"></ha-icon>
                ${locked ? "gesperrt" : "frei"}
              </span>
            </div>`;
        }
        body = `
          <div class="head ${unavailable ? "unavailable" : ""}">
            <span class="name">${name}</span>
          </div>
          <div class="temps ${unavailable ? "unavailable" : ""}">
            <span class="ist">${ist}</span>
            ${humText ? `<span class="hum"><ha-icon icon="mdi:water-percent"></ha-icon>${humText}</span>` : ""}
          </div>
          <div class="row">
            <span class="label">Soll-Temperatur</span>
            ${stepper}
          </div>
          <div class="row">
            <span class="label">Heizelement (PTC)</span>
            ${ptcButton}
          </div>
          ${lockRow}`;
      }

      root.innerHTML = `<style>${CSS}</style><ha-card>${body}</ha-card>`;
      const q = (sel) => root.querySelector(sel);
      if (q("#minus")) q("#minus").addEventListener("click", () => this._step(-1));
      if (q("#plus")) q("#plus").addEventListener("click", () => this._step(1));
      if (q("#ptc")) q("#ptc").addEventListener("click", () => this._toggle(ids.heating));
      if (q("#lock") && ids.lock && ids.lock.startsWith("switch.")) {
        q("#lock").addEventListener("click", () => this._toggle(ids.lock));
      }
    }
  }

  class ProxonRoomCardSlim extends ProxonRoomCard {
    constructor() {
      super();
      this._slim = true;
    }
  }

  if (!customElements.get("proxon-room-card")) {
    customElements.define("proxon-room-card", ProxonRoomCard);
  }
  if (!customElements.get("proxon-room-card-slim")) {
    customElements.define("proxon-room-card-slim", ProxonRoomCardSlim);
  }

  window.customCards = window.customCards || [];
  window.customCards.push(
    {
      type: "proxon-room-card",
      name: "Proxon Karte (detailliert)",
      description: "Ist-/Soll-Temperatur, PTC-Heizelement mit Status, Bedienteil-Sperre",
      preview: false,
    },
    {
      type: "proxon-room-card-slim",
      name: "Proxon Karte (kompakt)",
      description: "Ist-/Soll-Temperatur und PTC-Heizelement in einer Zeile",
      preview: false,
    }
  );
  console.info(`%c PROXON-ROOM-CARD %c v${VERSION}`, "color:white;background:#b71c1c", "");
})();
