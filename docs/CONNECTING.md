# Connecting friends

MCyard Server manages a local Java Edition server. It does not automatically open a
router port, install a VPN or create a public tunnel.

## On the same PC

In Minecraft Java, open **Multiplayer → Direct Connection** and enter
`localhost`. If the server uses a port other than `25565`, include it, for example
`localhost:25566`. Use the same Minecraft version as the server: **26.3**.

The bundled preset's management and backup mods run on the server. Friends do
not need MCyard Server or its management bridge installed on their PCs.

## On your home network

Friends on the same network connect to the host PC's LAN IPv4 address, with the
configured port when necessary. Windows Firewall may require allowing the Java
server on your private network. Keep the server's `server-ip` property blank.

## Over the internet with playit

One option is [playit.gg](https://playit.gg/). Only the server host runs its agent;
friends connect using the assigned public address.

1. Run the playit agent on the same PC as the server and link it to your account.
2. Create a **Minecraft Java** tunnel.
3. Set its local address to `127.0.0.1` and local port to the server's configured
   port, normally `25565`.
4. Keep **Proxy Protocol: None** for this preset.
5. Share playit's public Minecraft address with your friends.

Keep Minecraft, its manager and the playit agent running while people play. Use
the service's current documentation for its plan limits and routing options.
MCyard Server does not install or control the agent in version 0.1.0.

## Direct port forwarding

If your router has a reachable public IPv4 address, you can forward the server's
TCP port to the host PC and allow that port through the firewall. ISP-level NAT
(CGNAT) can prevent this from working; a public relay is an alternative. IPv6
hosting has different firewall/connectivity requirements.

A private friend server can use the whitelist: add friends through Players, then
enable the whitelist in Settings and restart. Keep `online-mode=true` for normal
Minecraft account authentication. Do not expose remote-management services just
to make the game reachable.

## Address and IP display

Behind a tunnel or proxy, Minecraft may see the relay/local address instead of
the player's original public IP. MCyard Server shows what the server reports; it
does not infer a hidden address. Do not enable PROXY protocol unless both ends
are explicitly configured to understand it.
