"use client";

/**
 * Live trace feed over the API's WebSocket (/ws/traces). Reconnects with backoff,
 * invalidates trace/stats queries on each event, and exposes the recent events
 * for the live indicator and activity feed.
 */

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import { WS_URL } from "@/lib/api";

export interface LiveEvent {
  type: "trace";
  trace_id: string;
  app: string;
  spans: number;
  received_at: number;
}

interface LiveState {
  connected: boolean;
  events: LiveEvent[];
  paused: boolean;
  setPaused: (p: boolean) => void;
}

const LiveContext = createContext<LiveState>({
  connected: false,
  events: [],
  paused: false,
  setPaused: () => {},
});

const MAX_EVENTS = 50;

export function LiveProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let closed = false;

    const connect = () => {
      try {
        ws = new WebSocket(WS_URL);
      } catch {
        schedule();
        return;
      }
      ws.onopen = () => {
        attempt = 0;
        setConnected(true);
      };
      ws.onclose = () => {
        setConnected(false);
        schedule();
      };
      ws.onerror = () => ws?.close();
      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data as string) as Omit<LiveEvent, "received_at">;
          if (data.type !== "trace") return;
          const ev: LiveEvent = { ...data, received_at: Date.now() };
          setEvents((prev) => [ev, ...prev].slice(0, MAX_EVENTS));
          if (!pausedRef.current) {
            void qc.invalidateQueries({ queryKey: ["traces"] });
            void qc.invalidateQueries({ queryKey: ["overview"] });
            void qc.invalidateQueries({ queryKey: ["apps"] });
            void qc.invalidateQueries({ queryKey: ["trace", data.trace_id] });
          }
        } catch {
          /* ignore malformed frames */
        }
      };
    };
    const schedule = () => {
      if (closed) return;
      const delay = Math.min(30_000, 1000 * 2 ** attempt++);
      timer = setTimeout(connect, delay);
    };
    connect();
    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      ws?.close();
    };
  }, [qc]);

  return (
    <LiveContext.Provider value={{ connected, events, paused, setPaused }}>
      {children}
    </LiveContext.Provider>
  );
}

export function useLive(): LiveState {
  return useContext(LiveContext);
}
