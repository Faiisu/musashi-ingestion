# Use shared session login for the operator console

Status: accepted

The original M21 contract and current implementation use a process-wide bearer token; this decision replaces that contract for the browser console and its API with a local shared `admin` account and opaque server-side sessions. The default username and password are `admin` and `00000000`, configurable through environment secrets, with no forced password change, login throttling, or account lockout; this deliberately favors a minimal single-operator setup over individual identity and stronger default credential controls, and must remain behind a restricted network. Sessions expire after 8 hours idle or 24 hours total and are invalidated on service restart; external API clients and backward compatibility with bearer tokens are out of scope.

Management access may be published on all host IPv4 interfaces for devices on a trusted private LAN. Add the LAN's exact `http://<private-ip>:<port>` origin to `MUSASHI_ALLOWED_ORIGINS`; keep the tailnet HTTPS origin separately allowlisted. HTTP cookies are not marked Secure, and LAN browser traffic is unencrypted. Never use wildcard origins or expose the interface to an untrusted network. `MUSASHI_PUBLIC_ORIGIN` remains the explicit HTTPS origin used by the TLS-terminating tailnet proxy.
