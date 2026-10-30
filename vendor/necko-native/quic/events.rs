use std::time::Instant;
use base64::{Engine, engine::general_purpose::STANDARD as B64};
use neqo_common::event::Provider;
use neqo_http3::{Http3ClientEvent as Event, Http3State};
use serde_json::{Value, json};
use crate::{Result, client::Session, crypto};

fn certificates(session: &Session) -> Vec<String> {
    session.client.peer_certificate().map(|certs| certs.iter().map(|c| B64.encode(c)).collect()).unwrap_or_default()
}
pub fn info(session: &Session) -> Value {
    let tls = session.client.tls_info().map(|info| json!({"backend":"NSS", "nss":crypto::version(),
        "profile":format!("firefox-{}",session.firefox), "alpn":info.alpn(), "version":info.version(),
        "cipher_suite":info.cipher_suite(), "resumed":info.resumed()}));
    json!({"tls":tls,"certificates":certificates(session)})
}
pub fn collect(session: &mut Session) -> Result<Value> {
    let mut events = Vec::new();
    for _ in 0..128 {
        let Some(event) = session.client.next_event() else { return Ok(json!({"events":events,"more":false})); };
        let value = match event {
            Event::AuthenticationNeeded => json!({"type":"auth","certificates":certificates(session)}),
            Event::EchFallbackAuthenticationNeeded {..} => json!({"type":"ech_retry"}),
            Event::StateChange(state) => match state {
                Http3State::Connected => json!({"type":"state","state":"connected"}),
                Http3State::GoingAway(last) => json!({"type":"state","state":"going_away","last":last.as_u64()}),
                Http3State::Closed(reason) | Http3State::Closing(reason) =>
                    json!({"type":"state","state":"closed","reason":format!("{reason:?}")}),
                _ => continue,
            },
            Event::HeaderReady {stream_id,headers,interim,fin} => json!({"type":"headers",
                "stream":stream_id.as_u64(),"interim":interim,"fin":fin,
                "headers":headers.iter().map(|h| json!([h.name(),B64.encode(h.value())])).collect::<Vec<_>>()}),
            Event::DataReadable {stream_id} => json!({"type":"readable","stream":stream_id.as_u64()}),
            Event::Reset {stream_id,error,..} => json!({"type":"reset","stream":stream_id.as_u64(),"error":error}),
            Event::StopSending {stream_id,error} => json!({"type":"stop_sending","stream":stream_id.as_u64(),"error":error}),
            Event::ResumptionToken(token) => json!({"type":"token","data":B64.encode(token.as_ref()),
                "expires_in":token.expiration_time().saturating_duration_since(Instant::now()).as_secs()}),
            _ => continue,
        };
        events.push(value);
    }
    Ok(json!({"events":events,"more":true}))
}
