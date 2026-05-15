export default function handler(req, res) {
  res.json({ key: process.env.ANTHROPIC_API_KEY || '' });
}
