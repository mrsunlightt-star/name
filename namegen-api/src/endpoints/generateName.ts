import { Bool, Num, OpenAPIRoute, Str } from "chanfana";
import { z } from "zod";
import { type AppContext } from "../types";

export class GenerateName extends OpenAPIRoute {
  schema = {
    tags: ["Name"],
    summary: "Generate Chinese name",
    request: {
      body: {
        content: {
          "application/json": {
            schema: z.object({
              style: Str({ required: false }),
              yourName: Str({ required: false }),
              genders: z.array(z.string()).optional(),
              styles: z.array(z.string()).optional(),
              count: Num({ required: false }),
              lang: Str({ required: false }),
            }),
          },
        },
      },
    },
    responses: {
      "200": {
        description: "Generated name",
        content: {
          "application/json": {
            schema: z.object({
              series: z.object({
                success: Bool(),
                result: z.object({
                  data: z.object({
                    style: z.string(),
                    name: z.string(),
                    meaning: z.string(),
                    story: z.string(),
                  }),
                }),
              }),
            }),
          },
        },
      },
    },
  };

  async handle(c: AppContext) {
    const data = await this.getValidatedData<typeof this.schema>();
    const preferredStyle = data.body?.style || (Array.isArray(data.body?.styles) && data.body?.styles[0]) || "poetic";
    const result = {
      style: preferredStyle,
      name: "苏若凡",
      meaning: "如飘逸之风，蕴含温润与雅致",
      story: "姓氏苏源远流长，名字若凡映照气质之淡定与风雅",
    };
    return {
      success: true,
      data: result,
    };
  }
}