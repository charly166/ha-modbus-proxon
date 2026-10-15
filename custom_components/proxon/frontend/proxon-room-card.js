/*
 * Proxon room cards for Home Assistant (shipped with the "HA Proxon FWT 2.0 Modbus" integration).
 *
 *   type: custom:proxon-room-card        # all-inclusive card
 *   type: custom:proxon-room-card-slim   # slim card
 *   entity: climate.buero                # the room's climate entity (required)
 *   name: Büro                           # optional
 *   # optional overrides (normally found automatically on the same device):
 *   heating: switch.buero_heizelement    # PTC enable switch
 *   status: binary_sensor.buero_heizelement_status
 *   lock: switch.buero_sperren_bedienteil
 *   humidity: sensor.proxon_luftfeuchte_wohnzimmer
 *
 * PTC icon: grey = off, orange = enabled, red = heating.
 */
(() => {
  const VERSION = "1";

  const TK = {
    heating: "proxon_zone_heizelement",
    status: "proxon_zone_heizelement_status",
    lock: "proxon_zone_tastensperre",
  };

  const CSS = `
    :host { display: block; }
    ha-card { padding: 12px 16px; }
    .head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .name { font-size: 1.1em; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .temps { display: flex; align-items: baseline; gap: 12px; margin: 8px 0 4px; }
    .ist { font-size: 2.2em; font-weight: 300; line-height: 1.1; }
    .hum { color: var(--secondary-text-color); }
    .row { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 8px; }
    .label { color: var(--secondary-text-color); }
    .stepper { display: flex; align-items: center; gap: 4px; }
    .stepper .val { min-width: 4.5em; text-align: center; font-size: 1.2em; }
    button { cursor: pointer; border: none; background: var(--secondary-background-color, #eee);
      color: var(--primary-text-color); border-radius: 50%; width: 36px; height: 36px;
      display: inline-flex; align-items: center; justify-content: center; padding: 0; }
    button[disabled] { opacity: 0.4; cursor: default; }
    button.ptc { background: transparent; width: 44px; height: 44px; }
    button.ptc ha-icon { --mdc-icon-size: 30px; }
    .chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 16px;
      background: var(--secondary-background-color, #eee); cursor: pointer; }
    .chip.static { cursor: default; }
    .status { display: inline-flex; align-items: center; gap: 6px; }
    .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    .slim { display: flex; align-items: center; gap: 10px; }
    .slim .name { flex: 1 1 auto; min-width: 0; }
    .slim .ist { font-size: 1.4em; }
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

    _step(direction) {
      const st = this._state(this._config.entity);
      if (!st) return;
      const a = st.attributes;
      const step = a.target_temp_step || 0.5;
      const current = Number(a.temperature);
      if (Number.isNaN(current)) return;
      let next = Math.round((current + direction * step) / step) * step;
      if (a.min_temp !== undefined) next = Math.max(next, a.min_temp);
      if (a.max_temp !== undefined) next = Math.min(next, a.max_temp);
      this._call("climate", "set_temperature", { entity_id: this._config.entity, temperature: next });
    }

    _toggle(id) {
      const domain = id.split(".")[0];
      this._call(domain, "toggle", { entity_id: id });
    }

    _fmt(value) {
      const n = Number(value);
      return Number.isNaN(n) ? "–" : `${n.toFixed(1).replace(".", ",")} °C`;
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

      const heatingSt = this._state(ids.heating);
      const statusSt = this._state(ids.status);
      const enabled = heatingSt ? heatingSt.state === "on" : climate.state === "heat";
      const heating = statusSt ? statusSt.state === "on" : false;
      const color = heating ? RED : enabled ? ORANGE : GREY;
      const label = heating ? "heizt" : enabled ? "freigegeben" : "aus";

      const ist = this._fmt(a.current_temperature);
      const soll = this._fmt(a.temperature);
      const min = a.min_temp;
      const max = a.max_temp;
      const cur = Number(a.temperature);
      const atMin = min !== undefined && cur <= min;
      const atMax = max !== undefined && cur >= max;
      const hum = this._state(ids.humidity);
      const humText = hum && hum.state !== "unavailable" && hum.state !== "unknown" ? `${hum.state} %` : "";

      const ptcButton = ids.heating
        ? `<button class="ptc" id="ptc" title="Heizelement ${label}"><ha-icon icon="mdi:radiator" style="color:${color}"></ha-icon></button>`
        : `<span class="status"><ha-icon icon="mdi:radiator" style="color:${color}"></ha-icon></span>`;
      const stepper = `
        <div class="stepper">
          <button id="minus" ${atMin || unavailable ? "disabled" : ""}><ha-icon icon="mdi:minus"></ha-icon></button>
          <span class="val">${soll}</span>
          <button id="plus" ${atMax || unavailable ? "disabled" : ""}><ha-icon icon="mdi:plus"></ha-icon></button>
        </div>`;

      let body;
      if (this._slim) {
        body = `
          <div class="slim ${unavailable ? "unavailable" : ""}">
            <span class="name">${name}</span>
            <span class="ist">${ist}</span>
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
            <span class="status" style="color:${color}"><span class="dot" style="background:${color}"></span>${label}</span>
          </div>
          <div class="temps ${unavailable ? "unavailable" : ""}">
            <span class="ist">${ist}</span>
            ${humText ? `<span class="hum"><ha-icon icon="mdi:water-percent"></ha-icon>${humText}</span>` : ""}
          </div>
          <div class="row">
            <span class="label">Soll</span>
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
      name: "Proxon Raum (komplett)",
      description: "Ist-/Soll-Temperatur, PTC-Heizelement mit Status, Bedienteil-Sperre",
      preview: false,
    },
    {
      type: "proxon-room-card-slim",
      name: "Proxon Raum (schlank)",
      description: "Ist-/Soll-Temperatur und PTC-Heizelement in einer Zeile",
      preview: false,
    }
  );
  console.info(`%c PROXON-ROOM-CARD %c v${VERSION}`, "color:white;background:#b71c1c", "");
})();
