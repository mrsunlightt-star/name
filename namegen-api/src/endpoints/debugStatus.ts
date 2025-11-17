import { Bool, OpenAPIRoute } from "chanfana";
import { z } from "zod";
import { type AppContext } from "../types";

export class DebugStatus extends OpenAPIRoute {
  schema = {
    tags: ["System"],
    summary: "Debug status",
    responses: {
      "200": {
        description: "Status",
        content: {
          "application/json": {
            schema: z.object({
              series: z.object({
                success: Bool(),
                result: z.object({
                  status: z.string(),
                  time: z.string(),
                }),
              }),
            }),
          },
        },
      },
    },
  };

  async handle(c: AppContext) {
    return {
      success: true,
      status: "ok",
      time: new Date().toISOString(),
    };
  }
}