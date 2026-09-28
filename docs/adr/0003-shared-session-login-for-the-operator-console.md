# Use shared session login for the operator console

Status: accepted

The original M21 contract and current implementation use a process-wide bearer token; this decision replaces that contract for the browser console and its API with a local shared `admin` account and opaque server-side sessions. The default username and password are `admin` and `00000000`, configurable through environment secrets, with no forced password change, login throttling, or account lockout; this deliberately favors a minimal single-operator setup over individual identity and stronger default credential controls, and must remain behind a restricted network. Sessions expire after 8 hours idle or 24 hours total and are invalidated on service restart; external API clients and backward compatibility with bearer tokens are out of scope.
