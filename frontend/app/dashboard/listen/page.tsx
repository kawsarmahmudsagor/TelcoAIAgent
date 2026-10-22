'use client';

import { Suspense, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Room, RoomEvent, Track, createLocalAudioTrack } from 'livekit-client';

type Status = 'idle' | 'connecting' | 'connected' | 'error' | 'disconnected';

function ListenInner() {
  const searchParams = useSearchParams();
  const initialRoom = searchParams.get('room') ?? '';

  const [roomName, setRoomName] = useState(initialRoom);
  const [status, setStatus] = useState<Status>('idle');
  const [micOn, setMicOn] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const roomRef = useRef<Room | null>(null);
  const audioContainerRef = useRef<HTMLDivElement>(null);

  function appendLog(line: string) {
    setLog((prev) => [...prev.slice(-50), line]);
  }

  async function connect() {
    if (!roomName.trim()) return;
    setStatus('connecting');
    setLog([]);
    try {
      const res = await fetch('/api/listen-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_name: roomName.trim() }),
      });
      if (!res.ok) throw new Error(await res.text());
      const { serverUrl, participantToken } = await res.json();

      const room = new Room();
      roomRef.current = room;

      room.on(RoomEvent.TrackSubscribed, (track, _pub, participant) => {
        appendLog(`track subscribed: ${track.kind} from ${participant.identity}`);
        if (track.kind === Track.Kind.Audio) {
          const el = track.attach();
          audioContainerRef.current?.appendChild(el);
        }
      });
      room.on(RoomEvent.TrackUnsubscribed, (track) => {
        track.detach().forEach((el) => el.remove());
      });
      room.on(RoomEvent.ParticipantConnected, (p) =>
        appendLog(`participant joined: ${p.identity}`)
      );
      room.on(RoomEvent.ParticipantDisconnected, (p) =>
        appendLog(`participant left: ${p.identity}`)
      );
      room.on(RoomEvent.Disconnected, () => {
        appendLog('disconnected');
        setStatus('disconnected');
      });

      await room.connect(serverUrl, participantToken);
      appendLog(`connected to room: ${roomName}`);
      setStatus('connected');
    } catch (err) {
      appendLog(`error: ${err instanceof Error ? err.message : String(err)}`);
      setStatus('error');
    }
  }

  async function toggleMic() {
    const room = roomRef.current;
    if (!room) return;
    if (micOn) {
      room.localParticipant.audioTrackPublications.forEach((pub) => {
        if (pub.track) room.localParticipant.unpublishTrack(pub.track);
      });
      setMicOn(false);
      appendLog('mic off');
    } else {
      const track = await createLocalAudioTrack();
      await room.localParticipant.publishTrack(track);
      setMicOn(true);
      appendLog('mic on — you can now talk as the client');
    }
  }

  function disconnect() {
    roomRef.current?.disconnect();
    roomRef.current = null;
    setMicOn(false);
    setStatus('idle');
  }

  useEffect(() => {
    return () => {
      roomRef.current?.disconnect();
    };
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold">Listen in on a call (dev only)</h1>
      <p className="text-muted-foreground text-sm">
        Join a call room by name to hear the agent speak and optionally talk back as a stand-in for
        the client &mdash; useful for testing scheduled cold calls, since nothing else joins that
        room automatically in this dev setup.
      </p>

      <div className="border-border flex flex-wrap items-end gap-3 rounded-lg border p-3">
        <div className="flex flex-col gap-1">
          <label className="text-muted-foreground text-xs">Room name</label>
          <input
            value={roomName}
            onChange={(e) => setRoomName(e.target.value)}
            placeholder="coldcall-..."
            className="border-border bg-background rounded border px-2 py-1 text-sm"
            disabled={status === 'connected' || status === 'connecting'}
          />
        </div>
        {status === 'connected' ? (
          <>
            <button
              onClick={toggleMic}
              className="bg-secondary text-secondary-foreground rounded px-3 py-1.5 text-sm"
            >
              {micOn ? 'Mute mic' : 'Unmute mic (talk as client)'}
            </button>
            <button
              onClick={disconnect}
              className="bg-destructive text-destructive-foreground rounded px-3 py-1.5 text-sm"
            >
              Disconnect
            </button>
          </>
        ) : (
          <button
            onClick={connect}
            disabled={status === 'connecting' || !roomName.trim()}
            className="bg-primary text-primary-foreground rounded px-3 py-1.5 text-sm disabled:opacity-50"
          >
            {status === 'connecting' ? 'Connecting...' : 'Connect'}
          </button>
        )}
        <span className="text-muted-foreground text-sm">status: {status}</span>
      </div>

      <div ref={audioContainerRef} />

      <div className="border-border bg-muted rounded-lg border p-3 font-mono text-xs">
        {log.length === 0 ? (
          <span className="text-muted-foreground">Log will appear here...</span>
        ) : (
          log.map((line, i) => <div key={i}>{line}</div>)
        )}
      </div>
    </div>
  );
}

export default function ListenPage() {
  return (
    <Suspense>
      <ListenInner />
    </Suspense>
  );
}
