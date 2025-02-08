import json
import logging
import os
from datetime import timedelta

import redis
import asyncio

from pymongo import MongoClient
from src.utils import call_youtube_api, parse
from src.video import Video

REDIS_URL = os.environ["REDIS_URL"]
MONGO_URL = os.environ["MONGO_URL"]
CACHE_TTL = 60 * 60 * 24  # 24 hours

redis_client = redis.from_url(REDIS_URL)
mongo_collection = MongoClient(os.environ["MONGO_URL"])["ytplaylistdb"][
    "ytplaylistcounts"
]


class Playlist:
    def __init__(
        self,
        playlist_id,
        custom_speed=None,
        start_range=None,
        end_range=None,
        youtube_api=None,
    ):
        self.playlist_id = playlist_id
        self.next_page = ""  # for pagination
        self.total_duration = timedelta(0)  # total duration
        self.custom_speed = custom_speed
        self.start_range = start_range
        self.end_range = end_range
        self.youtube_api = youtube_api

    async def do_async_work(self):

        found = self.get_video_list_from_cache(self.playlist_id)
        logging.info(f"Playlist {self.playlist_id} in cache: {found}")
        if not found:
            await self.get_video_ids_list()
            await self.get_videos_details()
            self.save_to_cache()

        self.available_count = sum([x.considered for x in self.videos])
        self.unavailable_count = len(self.videos) - self.available_count
        self.total_duration = sum([x.duration for x in self.videos], timedelta(0))
        self.average_duration = self.total_duration / self.available_count
        self.video_count = len(self.videos)
        self.start_range = max(1, self.start_range) if self.start_range else 1
        self.end_range = (
            min(self.available_count, self.end_range)
            if self.end_range
            else self.available_count
        )

        if self.start_range and self.end_range:
            self.videos_range = self.videos[self.start_range - 1 : self.end_range]
            self.total_duration = sum(
                [x.duration for x in self.videos_range], timedelta(0)
            )
            self.available_count = sum([x.considered for x in self.videos_range])
            self.unavailable_count = len(self.videos_range) - self.available_count
            self.average_duration = self.total_duration / self.available_count
            self.total_views = sum([int(x.views) for x in self.videos_range])
            self.average_views = self.total_views // self.available_count if self.available_count > 0 else 0

    def __repr__(self):
        return f"Playlist(playlist_id={self.playlist_id}, video_count={self.video_count}, total_duration={self.total_duration}, average_duration={self.average_duration})"

    def increment_playlist_count(self, playlist_id):
        try:
            mongo_collection.update_one(
                {"playlist_id": playlist_id}, {"$inc": {"count": 1}}, upsert=True
            )
        except Exception as e:
            logging.error(f"Error incrementing playlist count for {playlist_id}: {e}")

    def get_video_list_from_cache(self, playlist_id):
        key = f"playlist:{playlist_id}"
        self.increment_playlist_count(playlist_id)

        try:
            cached_data = redis_client.get(key)
            if cached_data:
                self.videos = [
                    Video(video_id=None, video_data=video_data)
                    for video_data in json.loads(cached_data)
                ]
                return True
        except Exception as e:
            logging.error(f"Error retrieving cache for {playlist_id}: {e}")

        return False

    def save_to_cache(self):
        try:
            jsonified_videos = json.dumps([video.to_dict() for video in self.videos])
            key = f"playlist:{self.playlist_id}"
            redis_client.setex(key, CACHE_TTL, jsonified_videos)
        except Exception as e:
            logging.error(f"Error saving to cache for playlist {self.playlist_id}: {e}")

    async def get_video_ids_list(self):

        self.video_ids = []
        while True:
            results = await call_youtube_api(
                "playlistItems",
                api=self.youtube_api,
                playlistId=self.playlist_id,
                pageToken=self.next_page,
            )
            self.video_ids += [x["contentDetails"]["videoId"] for x in results["items"]]

            if "nextPageToken" in results and len(self.video_ids) < 500:
                self.next_page = results["nextPageToken"]
            else:
                break

    async def get_videos_details(self):

        self.videos = []
        chunks = [self.video_ids[i : i + 50] for i in range(0, len(self.video_ids), 50)]
        tasks = [
            call_youtube_api("videos", api=self.youtube_api, video_ids=chunk)
            for chunk in chunks
        ]
        responses = await asyncio.gather(*tasks)

        for chunk, video_data in zip(chunks, responses):
            for video_id, data in zip(chunk, video_data["items"]):
                video = Video(video_id, data, self.custom_speed)
                self.videos.append(video)

    def get_output_string(self):
        # Basic playlist info section with title styling
        output_string = [
            f"📼 <strong>{self.playlist_name}</strong>",  # Bold title
            f"🆔 {self.playlist_id}",
            f"👤 {self.playlist_creator}",
            "",
        ]

        if self.video_count >= 500:
            output_string.extend([
                "⚠️ <strong>Warning</strong>: Number of videos limited to 500",  # Bold warning
                "",
            ])

        # Video statistics section with improved formatting and bold numbers
        output_string += [
            "📊 <strong>Statistics</strong>",
            f"• Total Videos: <strong>{self.available_count:,}</strong> (#{self.start_range} to #{self.end_range})",
            f"• Unavailable: <strong>{self.unavailable_count}</strong> video{'s' if self.unavailable_count != 1 else ''}",
            f"• Average Length: <strong>{parse(self.total_duration / self.available_count)}</strong> per video",
            f"• Views: <strong>{self.average_views:,}</strong> avg. | <strong>{self.total_views:,}</strong> total",
            "",
        ]

        # Watch time section with bold durations
        output_string += [
            "⏱️ <strong>Watch Time</strong>",
            f"• Normal Speed (1.00×): <strong>{parse(self.total_duration)}</strong>",
            f"• Fast (1.25×): <strong>{parse(self.total_duration / 1.25)}</strong>",
            f"• Faster (1.50×): <strong>{parse(self.total_duration / 1.5)}</strong>",
            f"• Even Faster (1.75×): <strong>{parse(self.total_duration / 1.75)}</strong>",
            f"• Maximum (2.00×): <strong>{parse(self.total_duration / 2)}</strong>",
            "",
        ]

        # Custom speed section with bold values
        if self.custom_speed:
            output_string += [
                "🎯 <strong>Custom Speed</strong>",
                f"• {self.custom_speed:.2f}×: <strong>{parse(self.total_duration / self.custom_speed)}</strong>",
                "",
            ]

        return output_string
