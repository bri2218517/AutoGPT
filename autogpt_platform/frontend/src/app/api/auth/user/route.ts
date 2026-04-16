import { getServerSupabase } from "@/lib/supabase/server/getServerSupabase";
import { NextResponse } from "next/server";

export async function GET() {
  const supabase = await getServerSupabase();
  const { data, error } = await supabase.auth.getUser();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 400 });
  }

  return NextResponse.json(data);
}

export async function PUT(request: Request) {
  try {
    const supabase = await getServerSupabase();
    const body = await request.json();
    const { email, full_name } = body as {
      email?: string;
      full_name?: string;
    };

    if (!email && !full_name) {
      return NextResponse.json(
        { error: "Email or full_name is required" },
        { status: 400 },
      );
    }

    const updatePayload: Parameters<typeof supabase.auth.updateUser>[0] = {};
    if (email) updatePayload.email = email;
    if (full_name) updatePayload.data = { full_name };

    const { data, error } = await supabase.auth.updateUser(updatePayload);

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { error: "Failed to update user" },
      { status: 500 },
    );
  }
}
