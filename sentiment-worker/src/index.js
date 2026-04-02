export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        },
      });
    }

    let text;

    if (request.method === 'POST') {
      const body = await request.json();
      text = body.text;
    } else {
      const url = new URL(request.url);
      text = url.searchParams.get('text');
    }

    if (!text) {
      return Response.json(
        { error: 'Missing "text" parameter. Send POST JSON body or GET ?text=...' },
        { status: 400 },
      );
    }

    const inputs = { text };

    const response = await env.AI.run(
      '@cf/huggingface/distilbert-sst-2-int8',
      inputs,
    );

    return Response.json(
      { inputs, response },
      {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Content-Type': 'application/json',
        },
      },
    );
  },
};
